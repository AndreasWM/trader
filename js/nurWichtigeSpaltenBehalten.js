function nurWichtigeSpaltenBehalten() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  
  // WICHTIG: Tragen Sie hier EXAKT die Überschriften der Spalten ein, 
  // die Sie BEHALTEN möchten:
  var wichtigeSpalten = [
    "Währung",
    "Anzahl / Nominal",
    "Bezeichnung",
    "Titel (kurz)",
    "ISIN",
    "WKN",
    "Einstandskurs Wertpapier",
    "Einstandskurs Devisen",
    "Aktueller Kurs Wertpapier",
    "Kursveränderung YTD in %",
    "Aktueller Kurs Devisen",
    "Kursdatum",
    "Aktueller Wert EUR",
    "Gesamterfolg %",
    "Unrealisierter Erfolg",
    "Einstandswert"
  ]; 

  
  // Alle Daten abfragen
  var data = sheet.getDataRange().getValues();
  if (data.length === 0) return;
  
  var headers = data[0]; // Erste Zeile (Spaltenüberschriften)
  
  // RÜCKWÄRTS durch die Spalten gehen (von rechts nach links).
  // Das ist nötig, weil sich beim Löschen einer Spalte die Indizes 
  // der nachfolgenden Spalten nach links verschieben.
  for (var i = headers.length - 1; i >= 0; i--) {
    var aktuelleUeberschrift = headers[i];
    
    // Überprüfen, ob die aktuelle Überschrift NICHT in der Whitelist steht
    if (wichtigeSpalten.indexOf(aktuelleUeberschrift) === -1) {
      sheet.deleteColumn(i + 1); // Google Apps Script ist 1-basiert (Spalte A = 1)
    }
  }
}