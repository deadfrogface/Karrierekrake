import 'package:flutter_test/flutter_test.dart';
import 'package:karrierekrake_mobile/app.dart';
import 'package:karrierekrake_mobile/data/app_database.dart';

void main() {
  testWidgets('app boots with in-memory DB and demo seed', (tester) async {
    final db = openTestDatabase();
    await tester.pumpWidget(
      KarrierekrakeMobileApp(database: db, seedAssets: false),
    );
    await tester.pump(); // start boot
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('Karrierekrake'), findsWidgets);
    await db.close();
  });
}
