TEST_FUNC(window_notifications_many_windows, {
    struct window *windows = calloc(1100, sizeof(*windows));
    if (!windows) return false;
    bool previous_version = _workspace_is_macos_version_goldengate;
    _workspace_is_macos_version_goldengate = true;
    table_init(&g_window_manager.window, 150, hash_wm, compare_wm);
    for (int i = 0; i < 1100; ++i) {
        windows[i].id = i+1;
        table_add(&g_window_manager.window, &windows[i].id, &windows[i]);
    }

    update_window_notifications();
    TEST_CHECK(notification_count, 1100);
    TEST_CHECK(notification_ids_valid, true);
    table_free(&g_window_manager.window);
    memset(&g_window_manager.window, 0, sizeof(g_window_manager.window));
    update_window_notifications();
    TEST_CHECK(notification_count, 0);

    _workspace_is_macos_version_goldengate = previous_version;
    free(windows);
})
