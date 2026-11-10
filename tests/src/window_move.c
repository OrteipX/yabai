TEST_FUNC(window_move_confirmation, {
    if (!ts_init(MEGABYTES(1))) return false;
    struct window window = {0};
    window.id = 1;
    membership_queries = 0;
    membership_ready_after = 3;
    TEST_CHECK(space_manager_wait_for_window_on_space(5, &window), true);
    TEST_CHECK(membership_queries, 3);
    ts_reset();

    membership_queries = 0;
    membership_ready_after = INT_MAX;
    TEST_CHECK(space_manager_wait_for_window_on_space(5, &window), false);
    TEST_CHECK(membership_queries > 0 && membership_queries <= 110, true);
    munmap(g_temp_storage.memory, g_temp_storage.size + getpagesize());
    memset(&g_temp_storage, 0, sizeof(g_temp_storage));
})
