import 'package:flutter/material.dart';

import 'data/app_database.dart';
import 'data/companion_repository.dart';
import 'ui/screens/shell.dart';

class KarrierekrakeMobileApp extends StatefulWidget {
  const KarrierekrakeMobileApp({
    super.key,
    this.database,
    this.seedAssets = true,
  });

  /// Injected DB for tests (memory).
  final AppDatabase? database;
  final bool seedAssets;

  @override
  State<KarrierekrakeMobileApp> createState() => _KarrierekrakeMobileAppState();
}

class _KarrierekrakeMobileAppState extends State<KarrierekrakeMobileApp> {
  late final AppDatabase _db;
  CompanionRepository? _repo;
  Object? _bootError;
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _db = widget.database ?? AppDatabase(openConnection());
    _boot();
  }

  Future<void> _boot() async {
    try {
      final repo = CompanionRepository(_db);
      if (widget.seedAssets) {
        final count = await _db.documentCount();
        if (count == 0) {
          await repo.seedFromAssetManifest(kDemoAssetFixtures);
        } else {
          await repo.loadFromDb();
        }
      } else {
        await repo.loadFromDb();
      }
      if (!mounted) return;
      setState(() {
        _repo = repo;
        _ready = true;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _bootError = e;
        _ready = true;
      });
    }
  }

  @override
  void dispose() {
    _db.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Karrierekrake',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0F6E56),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        visualDensity: VisualDensity.standard,
      ),
      home: !_ready
          ? const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            )
          : _bootError != null
              ? Scaffold(
                  body: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text('Startfehler: $_bootError'),
                    ),
                  ),
                )
              : CompanionShell(repo: _repo!),
    );
  }
}
