(function () {
  'use strict';
  var contents = document.querySelector('[data-contents]');
  if (contents) {
    var query = window.matchMedia('(min-width: 761px)');
    function setContents() { contents.open = query.matches; }
    setContents();
    if (query.addEventListener) query.addEventListener('change', setContents);
  }
  var printButton = document.querySelector('[data-print]');
  if (printButton) printButton.addEventListener('click', function () {
    var disclosures = Array.from(document.querySelectorAll('.faq'));
    var previous = disclosures.map(function (entry) { return entry.open; });
    disclosures.forEach(function (entry) { entry.open = true; });
    function restore() {
      disclosures.forEach(function (entry, index) { entry.open = previous[index]; });
      window.removeEventListener('afterprint', restore);
    }
    window.addEventListener('afterprint', restore);
    window.print();
  });
  var copy = document.querySelector('[data-copy-checksum]');
  if (copy) copy.addEventListener('click', function () {
    var checksum = document.getElementById('sha256').textContent.trim();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(checksum).then(function () {
        copy.textContent = 'Checksum copied';
        window.setTimeout(function () { copy.textContent = 'Copy checksum'; }, 2500);
      }).catch(function () { selectChecksum(); });
    } else selectChecksum();
    function selectChecksum() {
      var range = document.createRange();
      range.selectNodeContents(document.getElementById('sha256'));
      var selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      copy.textContent = 'Selected — copy with Ctrl+C';
    }
  });
}());
