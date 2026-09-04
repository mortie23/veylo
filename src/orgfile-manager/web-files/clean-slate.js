/**
 * Clean Slate - Strips core Power Pages styles & scripts (Bootstrap, Theme CSS, PortalBasicTheme)
 * to allow external custom design systems (e.g. HDS) to render cleanly without CSS conflicts.
 */
(function () {
  var BLOCKED_PATTERNS = ['bootstrap', 'portalbasictheme', 'theme.css'];

  function shouldStrip(href) {
    if (!href) return false;
    var lower = href.toLowerCase();
    for (var i = 0; i < BLOCKED_PATTERNS.length; i++) {
      if (lower.indexOf(BLOCKED_PATTERNS[i]) !== -1) {
        // Don't strip our own HDS or custom files that may coincidentally match
        if (lower.indexOf('hds') !== -1) return false;
        return true;
      }
    }
    return false;
  }

  function stripElement(el) {
    if (el.disabled !== undefined) el.disabled = true;
    el.parentNode && el.parentNode.removeChild(el);
  }

  function stripCoreStyles() {
    // Strip matching <link> stylesheets
    var links = document.querySelectorAll("link[rel='stylesheet'], link[type='text/css']");
    for (var i = 0; i < links.length; i++) {
      if (shouldStrip(links[i].getAttribute('href'))) {
        stripElement(links[i]);
      }
    }

    // Strip matching <script> elements (Bootstrap JS)
    var scripts = document.querySelectorAll("script[src]");
    for (var j = 0; j < scripts.length; j++) {
      var src = scripts[j].getAttribute('src') || '';
      if (src.toLowerCase().indexOf('bootstrap') !== -1) {
        stripElement(scripts[j]);
      }
    }
  }

  // Execute immediately to reduce Flash of Unstyled Content (FOUC)
  stripCoreStyles();

  // Execute on document ready to catch any late-injected core elements
  if (typeof $ !== 'undefined' && $.fn) {
    $(document).ready(stripCoreStyles);
  } else {
    document.addEventListener('DOMContentLoaded', stripCoreStyles);
  }

  // MutationObserver to catch dynamically injected Power Pages styles
  if (typeof MutationObserver !== 'undefined') {
    var observer = new MutationObserver(function (mutations) {
      for (var m = 0; m < mutations.length; m++) {
        var added = mutations[m].addedNodes;
        for (var n = 0; n < added.length; n++) {
          var node = added[n];
          if (node.nodeType !== 1) continue; // skip text nodes
          if (node.tagName === 'LINK' && shouldStrip(node.getAttribute('href'))) {
            stripElement(node);
          } else if (node.tagName === 'SCRIPT' && (node.getAttribute('src') || '').toLowerCase().indexOf('bootstrap') !== -1) {
            stripElement(node);
          }
        }
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });

    // Stop observing after page is fully loaded to avoid performance overhead
    window.addEventListener('load', function () {
      // Give a short delay to catch any final injections
      setTimeout(function () { observer.disconnect(); }, 2000);
    });
  }
})();
