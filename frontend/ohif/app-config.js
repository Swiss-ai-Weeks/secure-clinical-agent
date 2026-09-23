(function () {
  function dicomWebRoot() {
    try {
      var root = sessionStorage.getItem('p360.dicomweb') || '';
      if (root.indexOf('..') !== -1 || root.indexOf(':') !== -1 || root.indexOf('\\') !== -1) return '';
      if (!/^\/api\/media\/[^/]+\/dicom-web$/.test(root)) return '';
      return root;
    } catch (err) {
      return '';
    }
  }

  var root = dicomWebRoot();

  window.config = {
    routerBasename: '/ohif',
    showStudyList: false,
    showLoadingIndicator: true,
    maxNumberOfWebWorkers: 3,
    defaultDataSourceName: 'dicomweb',
    extensions: [],
    modes: [],
    dataSources: [
      {
        namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
        sourceName: 'dicomweb',
        configuration: {
          friendlyName: 'Patient360 signed study',
          name: 'Patient360',
          qidoRoot: root,
          wadoRoot: root,
          wadoUriRoot: root,
          qidoSupportsIncludeField: false,
          supportsFuzzyMatching: false,
          supportsWildcard: false,
          imageRendering: 'wadors',
          thumbnailRendering: 'wadors',
          enableStudyLazyLoad: true,
          omitQuotationForMultipartRequest: true
        }
      }
    ]
  };
})();
