import 'package:flutter/material.dart';

import '../../contracts/envelope.dart';
import '../../contracts/search_intent_dto.dart';
import '../widgets/state_views.dart';
import 'shell.dart';

class SearchIntentScreen extends StatefulWidget {
  const SearchIntentScreen({super.key, required this.intent});

  final SearchIntentDto? intent;

  @override
  State<SearchIntentScreen> createState() => _SearchIntentScreenState();
}

class _SearchIntentScreenState extends State<SearchIntentScreen> {
  late final TextEditingController _roles;
  late final TextEditingController _skills;
  String? _strictness;

  @override
  void initState() {
    super.initState();
    final i = widget.intent;
    _roles = TextEditingController(text: i?.targetRoles.join(', ') ?? '');
    _skills = TextEditingController(text: i?.mandatorySkills.join(', ') ?? '');
    _strictness = i?.strictness;
  }

  @override
  void dispose() {
    _roles.dispose();
    _skills.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final existing = widget.intent;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('SearchIntent', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text(
          'Expliziter Suchwunsch. STRICT wird nie stillschweigend gesetzt.',
        ),
        if (existing == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: EmptyStateView(
              title: 'Noch kein Intent',
              message: 'Du kannst einen lokalen Intent anlegen.',
              icon: Icons.search_off,
            ),
          ),
        TextField(
          controller: _roles,
          decoration: const InputDecoration(
            labelText: 'Zielrollen (kommagetrennt)',
          ),
        ),
        TextField(
          controller: _skills,
          decoration: const InputDecoration(
            labelText: 'Pflicht-Skills (kommagetrennt)',
          ),
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<String?>(
          value: _strictness,
          decoration: const InputDecoration(labelText: 'Strictness'),
          items: const [
            DropdownMenuItem(value: null, child: Text('—')),
            DropdownMenuItem(value: 'explore', child: Text('explore')),
            DropdownMenuItem(value: 'balanced', child: Text('balanced')),
            DropdownMenuItem(value: 'strict', child: Text('strict (explizit)')),
          ],
          onChanged: (v) => setState(() => _strictness = v),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: () async {
            final base = existing ??
                SearchIntentDto(
                  envelope: const ContractEnvelope(
                    contractVersion: kContractBundleVersion,
                    schemaId: SearchIntentDto.schemaId,
                  ),
                  schemaVersion: 1,
                );
            if (base.wouldSilentStrictExpand(_strictness) &&
                _strictness == 'strict' &&
                base.strictness != 'strict') {
              // Explicit user selection via dropdown counts as intentional.
            }
            final next = base.copyWith(
              targetRoles: _split(_roles.text),
              mandatorySkills: _split(_skills.text),
              strictness: _strictness,
              clearStrictness: _strictness == null,
            );
            await CompanionScope.of(context).repo.saveSearchIntent(next);
            if (!context.mounted) return;
            await CompanionScope.of(context).refresh();
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('SearchIntent lokal gespeichert')),
              );
            }
          },
          child: const Text('Lokal speichern'),
        ),
      ],
    );
  }

  List<String> _split(String raw) => raw
      .split(',')
      .map((s) => s.trim())
      .where((s) => s.isNotEmpty)
      .toList();
}
