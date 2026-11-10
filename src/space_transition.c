#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
// These waits execute on the serialized event thread. Keep a single monotonic
// two-second budget for an entire modern switch, including all its hops.
static bool space_manager_wait_for_space(uint32_t did, uint64_t sid, bool require_focus, uint64_t deadline)
{
    do {
        uint64_t current_sid = display_space_id(did);
        if (!current_sid || space_display_id(sid) != did) return false;
        bool focused = !require_focus;
        if (require_focus) {
            CFStringRef uuid = display_manager_active_display_uuid();
            if (uuid) {
                focused = display_id(uuid) == did;
                CFRelease(uuid);
            }
        }
        if (current_sid == sid && !display_manager_display_is_animating(did) && focused) return true;
        if (read_os_timer() >= deadline) break;
        usleep(10000);
    } while (read_os_timer() < deadline);

    debug("space focus timed out: display %u requested %llu current %llu\n", did, sid, display_space_id(did));
    return false;
}

static bool space_manager_post_modern_swipe(CGPoint point, float sign)
{
    CGEventRef events[3] = {0};
    CGEventRef companion = CGEventCreate(NULL);
    if (!companion) return false;
    CGEventSetIntegerValueField(companion, 55, 29); // kCGSEventGesture
    CGEventSetLocation(companion, point);

    // Build all phases before posting, so allocation/serialization failures
    // cannot leave the Dock with an unfinished gesture.
    int phases[] = {1, 2, 4}; // began, changed, ended
    bool result = false;
    for (int i = 0; i < 3; ++i) {
        CGEventRef event = CGEventCreate(NULL);
        if (!event) goto out;
        CGEventSetLocation(event, point);
        CGEventSetIntegerValueField(event, 55, 30);   // kCGSEventDockControl
        CGEventSetIntegerValueField(event, 110, 23); // kIOHIDEventTypeDockSwipe
        CGEventSetIntegerValueField(event, 123, 1);  // horizontal
        CGEventSetIntegerValueField(event, 132, phases[i]);
        CGEventSetIntegerValueField(event, 134, phases[i]);
        CGEventSetDoubleValueField(event, 138, 3.0);
        CGEventSetDoubleValueField(event, 169, (double)mach_absolute_time());
        CGEventSetDoubleValueField(event, 125, 0.1);
        CGEventSetDoubleValueField(event, 124, sign * 0.000016);
        if (phases[i] == 4) CGEventSetDoubleValueField(event, 129, sign * 9999.0);
        events[i] = space_gesture_augment_dock_swipe_event(event);
        CFRelease(event);
        if (!events[i]) goto out;
    }

    for (int i = 0; i < 3; ++i) {
        CGEventPost(kCGSessionEventTap, events[i]);
        CGEventPost(kCGSessionEventTap, companion);
        if (i < 2) usleep(10000);
    }
    result = true;
out:
    for (int i = 0; i < 3; ++i) if (events[i]) CFRelease(events[i]);
    CFRelease(companion);
    return result;
}

static bool space_manager_focus_space_using_modern_gesture(uint32_t new_did, uint64_t new_sid)
{
    uint64_t deadline = read_os_timer() + 2 * read_os_freq();
    int space_count = 0;
    uint64_t *spaces = display_space_list(new_did, &space_count);
    if (!spaces) return false;
    uint64_t current_sid = display_space_id(new_did);
    int current = -1, target = -1;
    for (int i = 0; i < space_count; ++i) {
        if (spaces[i] == current_sid) current = i;
        if (spaces[i] == new_sid) target = i;
    }
    if (current < 0 || target < 0) return false;

    Boolean valid = false;
    Boolean natural = CFPreferencesGetAppBooleanValue(CFSTR("com.apple.swipescrolldirection"), kCFPreferencesAnyApplication, &valid);
    float sign = target > current ? -1.0f : 1.0f;
    if (valid && !natural) sign = -sign;

    CGPoint point = display_center(new_did);
    if (current != target) {
        // Space swipes follow the cursor display, even with explicit locations.
        if (display_manager_cursor_display_id() != new_did && CGWarpMouseCursorPosition(point) != kCGErrorSuccess) return false;

        int step = target > current ? 1 : -1;
        for (int i = current + step; i != target + step; i += step) {
            int live_count = 0;
            uint64_t *live_spaces = display_space_list(new_did, &live_count);
            // Do not chase concurrent user gestures, display changes or a
            // reordered Space list with a stale direction or hop destination.
            if (read_os_timer() >= deadline || !live_spaces || live_count != space_count ||
                memcmp(live_spaces, spaces, space_count * sizeof(*spaces)) != 0 ||
                display_space_id(new_did) != spaces[i-step] ||
                display_manager_cursor_display_id() != new_did ||
                display_manager_display_is_animating(new_did)) return false;

            uint64_t hop_deadline = min(deadline, read_os_timer() + read_os_freq());
            if (!space_manager_post_modern_swipe(point, sign) ||
                !space_manager_wait_for_space(new_did, spaces[i], false, hop_deadline)) return false;
        }
    }

    if (display_space_id(new_did) != new_sid || space_display_id(new_sid) != new_did) return false;
    display_manager_focus_display(new_did, new_sid);
    return space_manager_wait_for_space(new_did, new_sid, true, deadline);
}

bool space_manager_focus_space_using_gesture(uint32_t new_did, uint64_t new_sid)
{
    if (!new_did || !new_sid || space_display_id(new_sid) != new_did) return false;
    if (workspace_is_macos_goldengate()) return space_manager_focus_space_using_modern_gesture(new_did, new_sid);

    int cur_index = space_manager_mission_control_index(display_space_id(new_did));
    int new_index = space_manager_mission_control_index(new_sid);
    if (cur_index <= 0 || new_index <= 0) return false;

    int count = abs(new_index - cur_index);
    if (count == 0) {
        display_manager_focus_display(new_did, new_sid);
        return true;
    }

    CGPoint point = display_center(new_did);
    uint32_t cur_did = display_manager_cursor_display_id();

    bool focus_display = cur_did != new_did;
    if (focus_display) CGWarpMouseCursorPosition(point);

    //
    // NOTE(asmvik): MacOS does not have an API that allows for space activation.
    // However, we can synthesize a sequence of high velocity gestures to skip the
    // animation instead.
    //
    // :Attribution
    // https://github.com/jurplel/InstantSpaceSwitcher
    // https://github.com/thenickdude/wacom-driver-fix/blob/bdfda9a788934c88d09d31ea6a42664b9ba1471e/Readme.md
    // Technique first observed in practice, and reverse-engineered from, BetterTouchTool.
    //

    CGEventRef event_dock_control = CGEventCreate(NULL);
    if (!event_dock_control) return false;

    float sign = (new_index - cur_index) > 0 ? 1.0 : -1.0;
    CGEventSetIntegerValueField(event_dock_control, /* kCGSEventTypeField            */  55, /* kCGSEventDockControl       */ 30);
    CGEventSetIntegerValueField(event_dock_control, /* kCGEventGestureHIDType        */ 110, /* kIOHIDEventTypeDockSwipe   */ 23);
    CGEventSetIntegerValueField(event_dock_control, /* kCGEventGestureSwipeMotion    */ 123, /* kCGGestureMotionHorizontal */  1);
    CGEventSetDoubleValueField(event_dock_control,  /* kCGEventGestureSwipeProgress  */ 124, sign);
    CGEventSetDoubleValueField(event_dock_control,  /* kCGEventGestureSwipeVelocityX */ 129, sign * 9999.0);

    for (int i = 0; i < count; ++i) {
        CGEventSetIntegerValueField(event_dock_control, /* kCGEventGesturePhase */ 132, /* kCGSGesturePhaseBegan */ 1);
        CGEventPost(kCGSessionEventTap, event_dock_control);
        CGEventSetIntegerValueField(event_dock_control, /* kCGEventGesturePhase */ 132, /* kCGSGesturePhaseEnded */ 4);
        CGEventPost(kCGSessionEventTap, event_dock_control);
    }
    CFRelease(event_dock_control);

    if (focus_display) {
        display_manager_set_active_display_id(new_did);
        if (space_manager_active_space() != new_sid) {
            CGPostMouseEvent(point, false, 1, true);
            CGPostMouseEvent(point, false, 1, false);
        }
    }

    return true;
}
#pragma clang diagnostic pop
