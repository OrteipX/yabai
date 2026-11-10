static mach_port_t test_connection_port(int cid)
{
    (void)cid;
    return MACH_PORT_NULL;
}

TEST_FUNC(window_sublevel_timeout, {
    bool previous_version = _workspace_is_macos_version_goldengate;
    mach_port_t (*previous_port_function)(int) = CGSGetConnectionPortById;
    _workspace_is_macos_version_goldengate = true;
    CGSGetConnectionPortById = test_connection_port;

    sublevel_reply_ok = false;
    TEST_CHECK(SLSGetWindowSubLevel__Internal(0, 1), 0);
    TEST_CHECK((sublevel_options & (MACH_SEND_TIMEOUT|MACH_RCV_TIMEOUT)) == (MACH_SEND_TIMEOUT|MACH_RCV_TIMEOUT), true);
    TEST_CHECK(sublevel_timeout, 250);
    sublevel_reply_ok = true;
    TEST_CHECK(SLSGetWindowSubLevel__Internal(0, 1), 7);

    CGSGetConnectionPortById = previous_port_function;
    _workspace_is_macos_version_goldengate = previous_version;
})
