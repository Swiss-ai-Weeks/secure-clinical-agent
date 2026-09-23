import { describe, expect, it } from 'vitest';
import {
  isAllowedDicomWebRoot,
  ohifViewerSrc,
  signedDicomWebRoot,
  signedMediaPath
} from '../../src/services/ohifSource';

describe('signedMediaPath', () => {
  it('accepts one signed media study and nothing else', () => {
    expect(signedMediaPath('/media/token/1.2.3')).toBe('/media/token/1.2.3');
    expect(signedMediaPath('/media/token/1.2.3?frame=1')).toBe('/media/token/1.2.3');
    expect(signedMediaPath('http://orthanc:8042/dicom-web/studies/1')).toBeNull();
    expect(signedMediaPath('http://minio:9000/reports/p_101')).toBeNull();
    expect(signedMediaPath('/media/token')).toBeNull();
    expect(signedMediaPath('/media/../orthanc/studies')).toBeNull();
  });
});

describe('signedDicomWebRoot', () => {
  it('builds only a signed /api/media dicom-web root', () => {
    expect(signedDicomWebRoot('/media/signed-token/study-1')).toBe('/api/media/signed-token/dicom-web');
    expect(signedDicomWebRoot('http://orthanc:8042/dicom-web/studies/1')).toBeNull();
    expect(signedDicomWebRoot('http://minio:9000/reports/p_101')).toBeNull();
    expect(signedDicomWebRoot('/media/../orthanc/studies')).toBeNull();
    expect(isAllowedDicomWebRoot('http://orthanc:8042/dicom-web')).toBe(false);
    expect(isAllowedDicomWebRoot('/api/media/signed-token/dicom-web')).toBe(true);
  });
});

describe('ohifViewerSrc', () => {
  it('opens OHIF on the signed study UID', () => {
    expect(ohifViewerSrc('1.2.840.study')).toBe('/ohif/viewer?StudyInstanceUIDs=1.2.840.study');
    expect(ohifViewerSrc('../orthanc')).toBeNull();
    expect(ohifViewerSrc('')).toBeNull();
  });
});
