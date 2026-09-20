import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Android manifest has OAuth deep link and disables backup', () {
    final xml = File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
    expect(xml.contains('de.karrierekrake.mobile'), isTrue);
    expect(xml.contains('android:autoVerify="true"'), isTrue);
    expect(xml.contains('allowBackup="false"'), isTrue);
    expect(xml.contains('android.webkit.WebView'), isFalse);
    expect(xml.contains('FlutterWebView'), isFalse);
  });

  test('Android data extraction rules exclude prefs/db', () {
    final xml = File('android/app/src/main/res/xml/data_extraction_rules.xml')
        .readAsStringSync();
    expect(xml.contains('sharedpref'), isTrue);
    expect(xml.contains('database'), isTrue);
  });

  test('iOS URL scheme and calendar usage strings', () {
    final plist = File('ios/Runner/Info.plist').readAsStringSync();
    expect(plist.contains('de.karrierekrake.mobile'), isTrue);
    expect(plist.contains('NSCalendarsUsageDescription'), isTrue);
  });

  test('iOS entitlements associated domains', () {
    final ent = File('ios/Runner/Runner.entitlements').readAsStringSync();
    expect(ent.contains('associated-domains'), isTrue);
    expect(ent.contains('applinks:app.karrierekrake.example'), isTrue);
  });

  test('Privacy Manifest present', () {
    expect(File('ios/Runner/PrivacyInfo.xcprivacy').existsSync(), isTrue);
  });

  test('auth security doc and push future work', () {
    final doc = File('../docs/mobile/auth_security.md').readAsStringSync();
    expect(doc.contains('No WebView OAuth'), isTrue);
    expect(doc.contains('Future Work'), isTrue);
    expect(doc.contains('UNSPECIFIED'), isTrue);
  });

  test('no client_secret treated as confidential in oauth config source', () {
    final src = File('lib/security/oauth_config.dart').readAsStringSync();
    expect(src.contains('NOT be treated as confidential') || src.contains('not a secret'),
        isTrue);
  });
}
