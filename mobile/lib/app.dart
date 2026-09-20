import 'package:flutter/material.dart';

/// Root widget for the companion app (scaffold UI only).
///
/// No PySide, no desktop services, no Windows OAuth assumptions.
class KarrierekrakeMobileApp extends StatelessWidget {
  const KarrierekrakeMobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Karrierekrake',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF18A999),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      home: const _CompanionHome(),
    );
  }
}

class _CompanionHome extends StatelessWidget {
  const _CompanionHome();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Karrierekrake')),
      body: const Padding(
        padding: EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Companion (Flutter)',
              style: TextStyle(fontSize: 28, fontWeight: FontWeight.w600),
            ),
            SizedBox(height: 12),
            Text(
              'Separate from the Windows desktop product. '
              'This shell consumes shared contracts only — '
              'no desktop UI port, no invented sync backend yet.',
            ),
          ],
        ),
      ),
    );
  }
}
