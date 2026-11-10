// These tests serialize events without posting them or changing the desktop.
TEST_FUNC(space_gesture_payload, {
    int phases[3];
    phases[0] = 1;
    phases[1] = 2;
    phases[2] = 4;
    for (int direction = -1; direction <= 1; direction += 2) {
        for (int i = 0; i < 3; ++i) {
            CGEventRef event = CGEventCreate(NULL);
            if (!event) return false;
            CGEventSetTimestamp(event, 123456789);
            CGEventSetIntegerValueField(event, 55, 30);
            CGEventSetIntegerValueField(event, 110, 23);
            CGEventSetIntegerValueField(event, 123, 1);
            CGEventSetIntegerValueField(event, 132, phases[i]);
            CGEventSetDoubleValueField(event, 124, direction * 0.000016);
            if (phases[i] == 4) CGEventSetDoubleValueField(event, 129, direction * 9999.0);

            size_t length = 0;
            uint8_t *bytes = space_gesture_generate_iohid_payload(event, &length);
            if (!bytes) { CFRelease(event); return false; }
            // Assert wire offsets independently of the packed C structs.
            TEST_CHECK((int)length, phases[i] == 4 ? 96 : 68);
            uint32_t value;
            memcpy(&value, bytes + 24, 4);
            TEST_CHECK(value, phases[i] == 4 ? 2 : 1); // event count
            memcpy(&value, bytes + 28, 4);
            TEST_CHECK(value, 40); // fluid event size
            memcpy(&value, bytes + 32, 4);
            TEST_CHECK(value, 23); // fluid event type
            memcpy(&value, bytes + 36, 4);
            TEST_CHECK(value, (uint32_t)phases[i] << 24);
            int32_t signed_value;
            memcpy(&signed_value, bytes + 64, 4);
            TEST_CHECK(signed_value, direction); // smallest signed 16.16 progress
            if (phases[i] == 4) {
                memcpy(&value, bytes + 72, 4);
                TEST_CHECK(value, 9); // velocity event type
                memcpy(&signed_value, bytes + 84, 4);
                TEST_CHECK(signed_value, direction * 9999 * 65536);
            }
            CGEventRef augmented = space_gesture_augment_dock_swipe_event(event);
            TEST_CHECK(augmented != NULL, true);
            if (augmented) {
                TEST_CHECK((int)CGEventGetIntegerValueField(augmented, 132), phases[i]);
                TEST_CHECK((int)CGEventGetIntegerValueField(augmented, 110), 23);
                uint8_t field[100];
                field[0] = 0;
                field[1] = (uint8_t)length;
                field[2] = 0x10;
                field[3] = 0x6d; // field 4205, big endian
                memcpy(field + 4, bytes, length);
                CFDataRef expected = CFDataCreate(NULL, field, length + 4);
                CFDataRef serialized = CGEventCreateData(NULL, augmented);
                if (!expected || !serialized) {
                    if (expected) CFRelease(expected);
                    if (serialized) CFRelease(serialized);
                    CFRelease(augmented);
                    free(bytes);
                    CFRelease(event);
                    return false;
                }
                CFRange match = CFDataFind(serialized, expected, CFRangeMake(0, CFDataGetLength(serialized)), 0);
                TEST_CHECK(match.location != kCFNotFound, true);
                CFRelease(serialized);
                CFRelease(expected);
                CFRelease(augmented);
            }
            free(bytes);
            CFRelease(event);
        }
    }
})

TEST_FUNC(space_gesture_invalid_target, {
    // Must reject invalid targets before touching WindowServer or the cursor.
    TEST_CHECK(space_manager_focus_space_using_gesture(0, 1), false);
    TEST_CHECK(space_manager_focus_space_using_gesture(1, 0), false);
    TEST_CHECK(space_gesture_augment_dock_swipe_event(NULL) == NULL, true);
})

TEST_FUNC(space_gesture_malformed_input, {
    CGEventRef event = CGEventCreate(NULL);
    if (!event) return false;
    uint8_t bytes[4] = {0};
    CFDataRef short_data = CFDataCreate(NULL, bytes, 3);
    bytes[3] = 3; // Unsupported format version, not version 2.
    CFDataRef unknown_data = CFDataCreate(NULL, bytes, 4);
    if (!short_data || !unknown_data) {
        if (short_data) CFRelease(short_data);
        if (unknown_data) CFRelease(unknown_data);
        CFRelease(event);
        return false;
    }
    TEST_CHECK(space_gesture_augment_dock_swipe_data(event, short_data) == NULL, true);
    TEST_CHECK(space_gesture_augment_dock_swipe_data(event, unknown_data) == NULL, true);
    TEST_CHECK(space_gesture_augment_dock_swipe_data(event, NULL) == NULL, true);
    CFRelease(short_data);
    CFRelease(unknown_data);
    CFRelease(event);

    TEST_CHECK(space_gesture_double_to_fixed1616(0.000001), 1);
    TEST_CHECK(space_gesture_double_to_fixed1616(-0.000001), -1);
    TEST_CHECK(space_gesture_double_to_fixed1616(INFINITY), INT32_MAX);
    TEST_CHECK(space_gesture_double_to_fixed1616(-INFINITY), INT32_MIN);
    TEST_CHECK(space_gesture_double_to_fixed1616(NAN), 0);
})
