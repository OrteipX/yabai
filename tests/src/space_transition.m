// Run the production transition state machine with a fake WindowServer and
// clock. Actual CGEvents are constructed/serialized, but none are posted.
#import <Cocoa/Cocoa.h>
#import <Carbon/Carbon.h>
#include <mach/mach_time.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../src/misc/space_gesture.h"

#define min(a,b) ((a) < (b) ? (a) : (b))
static uint64_t now, completion_time, current_sid, pending_sid;
static uint64_t route[4], snapshots[64][4];
static int snapshot_count, posts, creates, augments, owned, fail_create, fail_augment;
static bool modern, natural, animate, warp_fails, missing_uuid, drop, reorder;
static uint64_t completion_delay;
static uint32_t cursor_display, active_display;

static uint64_t read_os_timer(void) { return now; }
static uint64_t read_os_freq(void) { return 1000000000; }
static void debug(const char *fmt, ...) { (void)fmt; }
static int fake_sleep(useconds_t delay)
{
    now += delay * 1000ull;
    if (completion_time && now >= completion_time) {
        current_sid = pending_sid;
        completion_time = 0;
        if (reorder) { route[1] = 3; route[2] = 2; }
    }
    return 0;
}
static bool workspace_is_macos_goldengate(void) { return modern; }
static uint32_t space_display_id(uint64_t sid) { return sid >= 1 && sid <= 4 ? 7 : 0; }
static uint64_t display_space_id(uint32_t did) { return did == 7 ? current_sid : 0; }
static uint64_t *display_space_list(uint32_t did, int *count)
{
    if (did != 7 || snapshot_count == 64) return NULL;
    *count = 4;
    memcpy(snapshots[snapshot_count], route, sizeof(route));
    return snapshots[snapshot_count++];
}
static int space_manager_mission_control_index(uint64_t sid) { return (int)sid; }
static CGPoint display_center(uint32_t did) { (void)did; return CGPointMake(100, 100); }
static uint32_t display_manager_cursor_display_id(void) { return cursor_display; }
static bool display_manager_display_is_animating(uint32_t did) { (void)did; return animate; }
static CFStringRef display_manager_active_display_uuid(void)
{
    return missing_uuid ? NULL : CFRetain(CFSTR("display"));
}
static uint32_t display_id(CFStringRef uuid) { (void)uuid; return active_display; }
static void display_manager_focus_display(uint32_t did, uint64_t sid)
{
    (void)sid;
    active_display = did;
}
static void display_manager_set_active_display_id(uint32_t did) { active_display = did; }
static uint64_t space_manager_active_space(void) { return current_sid; }
static CGError fake_warp(CGPoint point)
{
    (void)point;
    if (warp_fails) return kCGErrorFailure;
    cursor_display = 7;
    return kCGErrorSuccess;
}
static Boolean fake_preference(CFStringRef key, CFStringRef app, Boolean *valid)
{
    (void)key; (void)app;
    *valid = true;
    return natural;
}
static CGEventRef fake_create(CGEventSourceRef source)
{
    if (++creates == fail_create) return NULL;
    CGEventRef result = CGEventCreate(source);
    if (result) ++owned;
    return result;
}
static CGEventRef fake_augment(CGEventRef event)
{
    if (++augments == fail_augment) return NULL;
    CGEventRef result = space_gesture_augment_dock_swipe_event(event);
    if (result) ++owned;
    return result;
}
static void fake_release(CFTypeRef object)
{
    if (CFGetTypeID(object) == CGEventGetTypeID()) --owned;
    CFRelease(object);
}
static void fake_post(CGEventTapLocation tap, CGEventRef event)
{
    (void)tap;
    ++posts;
    if (!modern || drop || CGEventGetIntegerValueField(event, 55) != 30 ||
        CGEventGetIntegerValueField(event, 132) != 4) return;
    double velocity = CGEventGetDoubleValueField(event, 129);
    int step = (velocity < 0) == natural ? 1 : -1;
    pending_sid = current_sid + step;
    if (completion_delay) completion_time = now + completion_delay;
    else current_sid = pending_sid;
}
#define usleep fake_sleep
#define CGWarpMouseCursorPosition fake_warp
#define CGEventCreate fake_create
#define CGEventPost fake_post
#define CFRelease fake_release
#define CFPreferencesGetAppBooleanValue fake_preference
#define space_gesture_augment_dock_swipe_event fake_augment
#include "../../src/space_transition.c"
#undef usleep
#undef CGWarpMouseCursorPosition
#undef CGEventCreate
#undef CGEventPost
#undef CFRelease
#undef CFPreferencesGetAppBooleanValue
#undef space_gesture_augment_dock_swipe_event

static void reset(void)
{
    now = completion_time = pending_sid = completion_delay = 0;
    current_sid = 1;
    for (int i = 0; i < 4; ++i) route[i] = i+1;
    snapshot_count = posts = creates = augments = owned = fail_create = fail_augment = 0;
    modern = natural = true;
    animate = warp_fails = missing_uuid = drop = reorder = false;
    cursor_display = active_display = 7;
}

#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "transition:%d: %s\n", __LINE__, #condition); return 1; } } while (0)
int main(void)
{
    reset();
    CHECK(space_manager_focus_space_using_gesture(7, 4));
    CHECK(current_sid == 4 && posts == 18 && owned == 0);
    reset(); natural = false;
    CHECK(space_manager_focus_space_using_gesture(7, 4));
    CHECK(current_sid == 4 && owned == 0);
    reset(); current_sid = 4;
    CHECK(space_manager_focus_space_using_gesture(7, 1));
    CHECK(current_sid == 1 && posts == 18 && owned == 0);
    reset(); active_display = 8;
    CHECK(space_manager_focus_space_using_gesture(7, 1));
    CHECK(posts == 0 && active_display == 7);
    reset(); cursor_display = 8; warp_fails = true;
    CHECK(!space_manager_focus_space_using_gesture(7, 2) && posts == 0);
    reset(); animate = true;
    CHECK(!space_manager_focus_space_using_gesture(7, 2) && posts == 0);
    reset(); missing_uuid = true;
    CHECK(!space_manager_focus_space_using_gesture(7, 1));
    CHECK(now <= 2000000000ull && posts == 0);
    reset(); drop = true;
    CHECK(!space_manager_focus_space_using_gesture(7, 4));
    CHECK(posts == 6 && now <= 1020000000ull && owned == 0);
    reset(); completion_delay = 750000000ull;
    CHECK(!space_manager_focus_space_using_gesture(7, 4));
    CHECK(now <= 2010000000ull && owned == 0);
    reset(); completion_delay = 10000000ull; reorder = true;
    CHECK(!space_manager_focus_space_using_gesture(7, 4));
    CHECK(posts == 6 && owned == 0);
    reset(); fail_create = 3;
    CHECK(!space_manager_focus_space_using_gesture(7, 2));
    CHECK(posts == 0 && owned == 0);
    reset(); fail_augment = 2;
    CHECK(!space_manager_focus_space_using_gesture(7, 2));
    CHECK(posts == 0 && owned == 0);
    reset(); modern = false;
    CHECK(space_manager_focus_space_using_gesture(7, 4));
    CHECK(posts == 6 && now == 0 && owned == 0);
    reset();
    CHECK(!space_manager_focus_space_using_gesture(0, 1));
    CHECK(!space_manager_focus_space_using_gesture(7, 0));
    CHECK(!space_manager_focus_space_using_gesture(8, 1));
    CHECK(posts == 0 && owned == 0);
    puts("14 transition scenarios passed (mocked WindowServer; no input posted)");
    return 0;
}
