// Read-only compatibility probe; does not start a daemon or post input events.
unsigned char __src_osax_payload[1];
unsigned int __src_osax_payload_len;
unsigned char __src_osax_loader[1];
unsigned int __src_osax_loader_len;

#include "../../src/manifest.m"

int main(void)
{
    @autoreleasepool {
        NSOperatingSystemVersion version = [[NSProcessInfo processInfo] operatingSystemVersion];
        printf("macOS %ld.%ld.%ld\n", version.majorVersion, version.minorVersion, version.patchVersion);
        const char *image = "/System/Library/PrivateFrameworks/SkyLight.framework/Versions/A/SkyLight";
        void *move = macho_find_symbol((char *)image, "__ZL54SLSPerformAsynchronousBridgedWindowManagementOperationP47SLSAsynchronousBridgedWindowManagementOperation");
        void *port = macho_find_symbol((char *)image, "_CGSGetConnectionPortById");
        Class cls = objc_getClass("SLSBridgedMoveWindowsToManagedSpaceOperation");
        SEL sel = sel_registerName("initWithWindows:spaceID:");
        printf("bridged move function: %s\n", move ? "found" : "missing (fallback required)");
        printf("bridged move initializer: %s\n", [cls instancesRespondToSelector:sel] ? "found" : "missing (fallback required)");
        printf("connection port function: %s\n", port ? "found" : "missing (fallback required)");
        Boolean valid = false;
        Boolean natural = CFPreferencesGetAppBooleanValue(CFSTR("com.apple.swipescrolldirection"), kCFPreferencesAnyApplication, &valid);
        printf("natural scrolling: %s\n", !valid ? "default (on)" : natural ? "on" : "off");
        return 0;
    }
}
