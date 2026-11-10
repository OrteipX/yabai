#import <Cocoa/Cocoa.h>
int main(void)
{
    @autoreleasepool {
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        for (int i = 0; i < 3; ++i) {
            NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(200 + i*80, 200 + i*60, 500, 350)
                styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskResizable
                backing:NSBackingStoreBuffered defer:NO];
            [window setTitle:[NSString stringWithFormat:@"yabai-macos27-disposable-%d", i]];
            [window setReleasedWhenClosed:NO];
            [window makeKeyAndOrderFront:nil];
        }
        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
}
