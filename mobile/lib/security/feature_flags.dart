/// Kill-switches for mobile integrations — rollback without uninstall.
library;

class MobileFeatureFlags {
  const MobileFeatureFlags({
    this.oauthEnabled = true,
    this.calendarWriteEnabled = false,
    this.remotePushEnabled = false,
    this.deepLinksEnabled = true,
    this.localRemindersEnabled = true,
  });

  final bool oauthEnabled;
  /// Remains false until sync/calendar-write transport is approved.
  final bool calendarWriteEnabled;
  /// Remains false — push backend UNSPECIFIED (PR37).
  final bool remotePushEnabled;
  final bool deepLinksEnabled;
  final bool localRemindersEnabled;

  MobileFeatureFlags copyWith({
    bool? oauthEnabled,
    bool? calendarWriteEnabled,
    bool? remotePushEnabled,
    bool? deepLinksEnabled,
    bool? localRemindersEnabled,
  }) {
    return MobileFeatureFlags(
      oauthEnabled: oauthEnabled ?? this.oauthEnabled,
      calendarWriteEnabled: calendarWriteEnabled ?? this.calendarWriteEnabled,
      remotePushEnabled: remotePushEnabled ?? this.remotePushEnabled,
      deepLinksEnabled: deepLinksEnabled ?? this.deepLinksEnabled,
      localRemindersEnabled:
          localRemindersEnabled ?? this.localRemindersEnabled,
    );
  }

  /// Commercial defaults: OAuth on, write/push off until approved.
  static const commercialSafe = MobileFeatureFlags();
}
