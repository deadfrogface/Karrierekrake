/// Mobile capability matrix — mirrors contracts/permissions.json.
/// Sync transport remains UNSPECIFIED; no network writes.
library;

enum MobileWriteMode {
  none,
  full,
  limited,
  appendOnly,
  selectSlot,
  draftOnly,
}

class ObjectPermission {
  const ObjectPermission({
    required this.schemaId,
    required this.mobileRead,
    required this.mobileWrite,
    required this.desktopAuthoritative,
    required this.offlineCacheable,
    required this.pii,
  });

  final String schemaId;
  final bool mobileRead;
  final MobileWriteMode mobileWrite;
  final bool desktopAuthoritative;
  final bool offlineCacheable;
  final bool pii;
}

const kPermissions = <String, ObjectPermission>{
  'profile': ObjectPermission(
    schemaId: 'karrierekrake.profile',
    mobileRead: true,
    mobileWrite: MobileWriteMode.full,
    desktopAuthoritative: false,
    offlineCacheable: true,
    pii: true,
  ),
  'search_intent': ObjectPermission(
    schemaId: 'karrierekrake.search_intent',
    mobileRead: true,
    mobileWrite: MobileWriteMode.full,
    desktopAuthoritative: false,
    offlineCacheable: true,
    pii: false,
  ),
  'job': ObjectPermission(
    schemaId: 'karrierekrake.job',
    mobileRead: true,
    mobileWrite: MobileWriteMode.none,
    desktopAuthoritative: true,
    offlineCacheable: true,
    pii: false,
  ),
  'application_case': ObjectPermission(
    schemaId: 'karrierekrake.application_case',
    mobileRead: true,
    mobileWrite: MobileWriteMode.limited,
    desktopAuthoritative: true,
    offlineCacheable: true,
    pii: true,
  ),
  'lifecycle_event': ObjectPermission(
    schemaId: 'karrierekrake.lifecycle_event',
    mobileRead: true,
    mobileWrite: MobileWriteMode.appendOnly,
    desktopAuthoritative: true,
    offlineCacheable: true,
    pii: false,
  ),
  'calendar_proposal': ObjectPermission(
    schemaId: 'karrierekrake.calendar_proposal',
    mobileRead: true,
    mobileWrite: MobileWriteMode.selectSlot,
    desktopAuthoritative: true,
    offlineCacheable: true,
    pii: false,
  ),
  'reply_draft': ObjectPermission(
    schemaId: 'karrierekrake.reply_draft',
    mobileRead: true,
    mobileWrite: MobileWriteMode.draftOnly,
    desktopAuthoritative: true,
    offlineCacheable: true,
    pii: true,
  ),
  'guenther_result': ObjectPermission(
    schemaId: 'karrierekrake.guenther_result',
    mobileRead: true,
    mobileWrite: MobileWriteMode.none,
    desktopAuthoritative: true,
    offlineCacheable: true,
    pii: false,
  ),
};

bool canWrite(String objectKey) {
  final p = kPermissions[objectKey];
  if (p == null) return false;
  return p.mobileWrite != MobileWriteMode.none;
}

/// Send / calendar write require approved sync transport — blocked in MVP.
bool isExternalActionBlocked(String action) {
  switch (action) {
    case 'send_email':
    case 'calendar_write':
    case 'job_scrape':
    case 'apply_bot':
    case 'phi_download':
    case 'cloud_sync':
      return true;
    default:
      return false;
  }
}
