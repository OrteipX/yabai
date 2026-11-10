unsigned char __src_osax_payload[1];
unsigned int __src_osax_payload_len;
unsigned char __src_osax_loader[1];
unsigned int __src_osax_loader_len;

// Capture notification subscriptions without sending anything to WindowServer.
#define SLSRequestNotificationsForWindows test_request_notifications
#define mach_msg test_mach_msg
#define SLSCopySpacesForWindows test_copy_spaces_for_windows
#include "../../src/manifest.m"
#undef SLSRequestNotificationsForWindows
#undef mach_msg
#undef SLSCopySpacesForWindows

static int membership_queries, membership_ready_after;
CFArrayRef test_copy_spaces_for_windows(int cid, int selector, CFArrayRef windows)
{
    (void)cid; (void)selector; (void)windows;
    int64_t sid = ++membership_queries >= membership_ready_after ? 5 : 4;
    CFNumberRef number = CFNumberCreate(NULL, kCFNumberSInt64Type, &sid);
    CFArrayRef result = CFArrayCreate(NULL, (const void **)&number, 1, &kCFTypeArrayCallBacks);
    CFRelease(number);
    return result;
}

static mach_msg_option_t sublevel_options;
static mach_msg_timeout_t sublevel_timeout;
static bool sublevel_reply_ok;
mach_msg_return_t test_mach_msg(mach_msg_header_t *header, mach_msg_option_t options,
                               mach_msg_size_t send_size, mach_msg_size_t receive_size,
                               mach_port_name_t receive_name, mach_msg_timeout_t timeout,
                               mach_port_name_t notify)
{
    (void)send_size; (void)receive_size; (void)receive_name; (void)notify;
    sublevel_options = options;
    sublevel_timeout = timeout;
    if (!sublevel_reply_ok) return MACH_RCV_TIMED_OUT;
    header->msgh_size = 48;
    int32_t sublevel = 7;
    memcpy((char *)header + 36, &sublevel, sizeof(sublevel));
    return KERN_SUCCESS;
}

static int notification_count;
static bool notification_ids_valid;
CGError test_request_notifications(int cid, uint32_t *windows, int count)
{
    (void)cid;
    notification_count = count;
    notification_ids_valid = true;
    for (int i = 0; i < count; ++i) {
        if (windows[i] < 1 || windows[i] > 1100) notification_ids_valid = false;
    }
    return kCGErrorSuccess;
}

#define TEST_SIG(name) bool test_##name(void)
typedef TEST_SIG(function);

#define TEST_FUNC(name, code) static TEST_SIG(name) { char *test_name = #name; bool result = true; {code} return result; }
#define TEST_CHECK(r, e) if ((r) != (e)) { printf("                   \e[1;33m%s\e[m\e[1;31m#%d %s == %s\e[m \e[1;31m(%d == %d)\e[m\n", test_name, __LINE__, #r, #e, r, e); result = false; }

#include "area.c"
#include "gesture.c"
#include "notifications.c"
#include "sublevel.c"
#include "window_move.c"

#define TEST_ENTRY(name) { #name, test_##name },
#define TEST_LIST                                              \
    TEST_ENTRY(display_area_is_in_direction)                   \
    TEST_ENTRY(closest_display_in_direction)                   \
    TEST_ENTRY(space_gesture_payload)                          \
    TEST_ENTRY(space_gesture_invalid_target)                    \
    TEST_ENTRY(window_notifications_many_windows)              \
    TEST_ENTRY(space_gesture_malformed_input)                    \
    TEST_ENTRY(window_sublevel_timeout)                         \
    TEST_ENTRY(window_move_confirmation)

static struct {
    char *name;
    test_function *func;
} tests[] = {
    TEST_LIST
};

int main(int argc, char **argv)
{
    int succeeded = 0;
    int failed = 0;
    int total = array_count(tests);
    printf("\e[1;34m -- Running %d tests\e[m\n\n", total);

    uint64_t cpu_freq  = read_cpu_freq();
    uint64_t begin_tsc = read_cpu_timer();

    for (int i = 0; i < total; ++i) {
        uint64_t tsc = read_cpu_timer();
        bool result = tests[i].func();
        double ms_elapsed = 1000.0 * (double)(read_cpu_timer() - tsc) / (double)cpu_freq;

        printf("(%0.4fms) %s \e[1;33m%s\e[m\n", ms_elapsed, result ? "\e[1;32msuccess\e[m" : " \e[1;31mfailed\e[m", tests[i].name);
        if (result) ++succeeded; else ++failed;
    }

    double ms_elapsed = 1000.0 * (double)(read_cpu_timer() - begin_tsc) / (double)cpu_freq;
    printf("\n\e[1;34m -- Completed (%0.4fms)\e[m\n", ms_elapsed);
    printf("\t%d \e[1;32msucceeded\e[m\n", succeeded);
    printf("\t%d \e[1;31mfailed\e[m\n", failed);
    printf("\t%d \e[1;33mtotal\e[m\n", total);

    return total == succeeded ? EXIT_SUCCESS : EXIT_FAILURE;
}
