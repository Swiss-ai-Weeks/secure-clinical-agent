/** OHIF may load one signed study. Orthanc and object storage are not viewer URLs. */

const SIGNED_MEDIA = /^\/media\/[^/]+\/[^/]+$/;
const SIGNED_DICOMWEB = /^\/api\/media\/[^/]+\/dicom-web$/;
const STUDY_UID = /^[0-9A-Za-z._-]{1,64}$/;

export const DICOMWEB_STORAGE_KEY = 'p360.dicomweb';

export function signedMediaPath(url: string): string | null {
  const path = url.split('?')[0].split('#')[0];
  if (!SIGNED_MEDIA.test(path)) return null;
  if (path.includes('..') || path.includes('\\') || path.includes(':')) return null;
  return path;
}

export function signedDicomWebRoot(url: string): string | null {
  const path = signedMediaPath(url);
  if (!path) return null;
  const token = path.split('/')[2];
  if (!token) return null;
  const root = `/api/media/${token}/dicom-web`;
  return isAllowedDicomWebRoot(root) ? root : null;
}

export function isAllowedDicomWebRoot(root: string): boolean {
  if (root.includes('..') || root.includes('\\') || root.includes(':') || root.includes('//')) return false;
  return SIGNED_DICOMWEB.test(root);
}

export function storeDicomWebRoot(root: string): boolean {
  if (!isAllowedDicomWebRoot(root)) return false;
  sessionStorage.setItem(DICOMWEB_STORAGE_KEY, root);
  return true;
}

export function ohifViewerSrc(studyInstanceUid: string): string | null {
  if (!STUDY_UID.test(studyInstanceUid)) return null;
  return `/ohif/viewer?StudyInstanceUIDs=${encodeURIComponent(studyInstanceUid)}`;
}
