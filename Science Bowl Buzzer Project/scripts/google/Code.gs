// Bound to the Science Bowl Data Center spreadsheet. IDs filled during setup.
const SETTINGS = {
  gamesFolder: 'YOUR_GAMES_FOLDER_ID',
  roster: 'YOUR_ROSTER_SPREADSHEET_ID',
  center: 'YOUR_DATA_CENTER_SPREADSHEET_ID'
};
const ATTEMPT_HEADERS = ['Attempt ID','Game ID','Game','Question','Subject','Port','Player ID','Player','Result','Interrupt','Correct','Time (s)','Recorded at'];
const SUBJECT_TABS = ['ALL','Biology','Physics','Math','Earth and Space','Chemistry','Energy'];
function subjectGroup(subject) {
  const key=String(subject || '').trim().toUpperCase();
  if (['EARTH SCIENCE','ASTRONOMY','EARTH AND SPACE','EARTH AND SPACE SCIENCE'].includes(key)) return 'Earth and Space';
  if (['GENERAL SCIENCE','ENERGY'].includes(key)) return 'Energy';
  return ({BIOLOGY:'Biology',PHYSICS:'Physics',MATH:'Math',MATHEMATICS:'Math',CHEMISTRY:'Chemistry'})[key] || 'Unmapped';
}
const SUMMARY_HEADERS = ['Player ID','Player','Subject','Buzzes','Correct','Wrong','Accuracy','Known timing','Interrupts','Interrupt rate','Interrupt correct','Interrupt accuracy','Unknown timing','Games'];

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Science Bowl')
    .addItem('Set up connection key', 'setupConnection')
    .addItem('Refresh analysis', 'refreshFromMenu').addToUi();
}

function setupConnection() {
  const props = PropertiesService.getScriptProperties();
  let token = props.getProperty('CONNECTION_KEY');
  if (!token) {
    token = Utilities.getUuid().replace(/-/g,'') + Utilities.getUuid().replace(/-/g,'');
    props.setProperty('CONNECTION_KEY', token);
  }
  SpreadsheetApp.getUi().alert('Connection key',
    'Paste this key into Connect Google on the Pi dashboard. Keep it private.\n\n' + token,
    SpreadsheetApp.getUi().ButtonSet.OK);
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    const request = JSON.parse(e.postData.contents);
    const key = PropertiesService.getScriptProperties().getProperty('CONNECTION_KEY');
    if (!key || typeof request.token !== 'string' || request.token !== key) throw new Error('Invalid connection key');
    lock.waitLock(20000);
    let result;
    if (request.action === 'roster') result = {players: readRoster()};
    else if (request.action === 'sync') result = syncGame(request.game);
    else if (request.action === 'refresh') result = refreshAnalysis();
    else if (request.action === 'status') result = {roster_url: SpreadsheetApp.openById(SETTINGS.roster).getUrl(),center_url: SpreadsheetApp.openById(SETTINGS.center).getUrl()};
    else throw new Error('Unknown action');
    return output({ok:true,...result});
  } catch (error) {
    return output({ok:false,error:String(error.message || error)});
  } finally { if (lock.hasLock()) lock.releaseLock(); }
}
function doGet() { return output({ok:false,error:'Use the authenticated Science Bowl dashboard connection.'}); }
function output(value) { return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON); }
function text(value) {
  if (value === null || value === undefined) return '';
  if (typeof value !== 'string') return value;
  return /^[=+@-]/.test(value) ? "'" + value : value;
}
function writeGrid(book, name, rows) {
  const sheet = book.getSheetByName(name) || book.insertSheet(name);
  const oldLast = sheet.getLastRow();
  const oldWidth = sheet.getLastColumn();
  if (rows.length > sheet.getMaxRows()) sheet.insertRowsAfter(sheet.getMaxRows(),rows.length-sheet.getMaxRows());
  if (rows[0].length > sheet.getMaxColumns()) sheet.insertColumnsAfter(sheet.getMaxColumns(),rows[0].length-sheet.getMaxColumns());
  sheet.getRange(1,1,rows.length,rows[0].length).setValues(rows.map(r=>r.map(text)));
  if (oldWidth > rows[0].length) sheet.getRange(1,rows[0].length+1,Math.max(oldLast,rows.length),oldWidth-rows[0].length).clearContent();
  if (oldLast > rows.length) sheet.getRange(rows.length+1,1,oldLast-rows.length,sheet.getLastColumn()).clearContent();
  sheet.setFrozenRows(1);
  sheet.getRange(1,1,1,rows[0].length).setBackground('#eeeeee').setFontWeight('bold').setWrap(true);
  sheet.setRowHeight(1,40);
  return sheet;
}
function readRoster() {
  const sheet = SpreadsheetApp.openById(SETTINGS.roster).getSheetByName('Mapping');
  if (!sheet) throw new Error('Player Names sheet needs a Mapping tab');
  const rows = sheet.getRange(2,1,16,3).getDisplayValues();
  return rows.map(r=>({port:r[0],person_id:r[1],name:r[2]}));
}
function syncGame(game) {
  if (!game || !/^[a-f0-9-]+:\d+$/.test(game.game_key)) throw new Error('Invalid game ID');
  if (!Array.isArray(game.attempts) || !Array.isArray(game.questions) || !game.questions.length) throw new Error('No recorded questions to sync');
  if (game.missing_subjects.length) throw new Error('Import subjects for questions '+game.missing_subjects.join(', ')+' before syncing');
  const folder = DriveApp.getFolderById(SETTINGS.gamesFolder);
  const filename = 'Game ' + game.game_key;
  const files = folder.getFilesByName(filename);
  let book;
  if (files.hasNext()) {
    book = SpreadsheetApp.openById(files.next().getId());
    if (files.hasNext()) throw new Error('Duplicate game files found; resolve them before syncing');
  } else {
    book = SpreadsheetApp.create(filename);
    DriveApp.getFileById(book.getId()).moveTo(folder);
  }
  const rows = game.attempts.map(a=>[
    a.attempt_key,game.game_key,game.name,a.question_number,a.subject || '',a.player_id ? 'P'+a.player_id : '',
    a.person_id,a.player_name,a.result,a.interrupt,a.correct,
    a.elapsed_ms == null ? '' : a.elapsed_ms/1000,a.created_at]);
  const attemptSheet = writeGrid(book,'Attempts',[ATTEMPT_HEADERS,...rows]);
  attemptSheet.setColumnWidths(1,3,220); attemptSheet.setColumnWidth(5,190);
  attemptSheet.setColumnWidths(7,2,170);
  if (rows.length) attemptSheet.getRange(2,12,rows.length,1).setNumberFormat('0.00');
  writeGrid(book,'Questions', [['Question','Subject','Result','Finalized at'],...game.questions.map(q=>[
    q.question_number,q.subject,q.final_result || 'In progress',q.finalized_at || ''])]);
  writeGrid(book,'Info', [['Key','Value'],['schema','science-bowl-v2'],['game_key',game.game_key],['name',game.name],
    ['created_at',game.created_at],['pdf_url',game.pdf_url],['last_synced',new Date().toISOString()]]);
  const blank = book.getSheetByName('Sheet1'); if (blank && blank.getLastRow() === 0) book.deleteSheet(blank);
  SpreadsheetApp.flush();
  const analysis = refreshAnalysis();
  return {url:book.getUrl(),title:game.name,attempts:rows.length,...analysis};
}

function refreshFromMenu() {
  const lock=LockService.getScriptLock(); lock.waitLock(20000);
  try { const r=refreshAnalysis(); SpreadsheetApp.getUi().alert('Updated '+r.games+' games and '+r.buzzes+' answered buzzes.'); }
  finally {lock.releaseLock();}
}
function refreshAnalysis() {
  const folder = DriveApp.getFolderById(SETTINGS.gamesFolder);
  const files = folder.getFilesByType(MimeType.GOOGLE_SHEETS);
  const attempts=[], games=[], seenGames=new Set(), seenAttempts=new Set();
  while (files.hasNext()) {
    const file=files.next(), book=SpreadsheetApp.openById(file.getId()), info=book.getSheetByName('Info');
    if (!info) continue;
    const meta=Object.fromEntries(info.getDataRange().getValues().slice(1));
    if (meta.schema !== 'science-bowl-v2') continue;
    if (seenGames.has(meta.game_key)) throw new Error('Duplicate game ID in Games folder: '+meta.game_key);
    seenGames.add(meta.game_key);
    const source=book.getSheetByName('Attempts');
    const values=source.getDataRange().getValues();
    // Migrate existing game exports while retaining every attempt.
    if (values[0][8] === 'Team') {
      values.forEach(row=>row.splice(8,1));
      writeGrid(book,'Attempts',values);
    }
    if (JSON.stringify(values[0]) !== JSON.stringify(ATTEMPT_HEADERS)) throw new Error('Unexpected columns in '+file.getName());
    for (const row of values.slice(1)) {
      if (!row[0]) continue;
      if (seenAttempts.has(row[0])) throw new Error('Duplicate attempt ID: '+row[0]);
      seenAttempts.add(row[0]); attempts.push(row);
    }
    const missing=[...new Set(values.slice(1).filter(r=>r[0]&&!r[4]).map(r=>r[3]))].join(', ');
    games.push([meta.game_key,meta.name,meta.created_at,meta.pdf_url,book.getUrl(),meta.last_synced,missing]);
  }
  attempts.sort((a,b)=>String(a[12]).localeCompare(String(b[12])) || String(a[0]).localeCompare(String(b[0])));
  const grouped=new Map();
  let buzzes=0;
  for (const a of attempts) {
    if (!a[5] || !['Correct','Wrong'].includes(a[8])) continue;
    buzzes++;
    for (const subject of ['ALL',subjectGroup(a[4])]) {
      const key=JSON.stringify([a[6],subject]);
      const g=grouped.get(key)||{id:a[6],name:a[7],subject,buzzes:0,correct:0,wrong:0,known:0,interrupts:0,icorrect:0,unknown:0,games:new Set()};
      g.name=a[7]; g.buzzes++; g.correct+=a[8]==='Correct'?1:0; g.wrong+=a[8]==='Wrong'?1:0;
      if (a[9]===true || a[9]===false) {g.known++; if(a[9]){g.interrupts++;if(a[8]==='Correct')g.icorrect++;}}
      else g.unknown++;
      g.games.add(a[1]);grouped.set(key,g);
    }
  }
  const summary=[...grouped.values()].sort((a,b)=>a.name.localeCompare(b.name)||a.id.localeCompare(b.id)||a.subject.localeCompare(b.subject));
  const center=SpreadsheetApp.openById(SETTINGS.center);
  writeGrid(center,'All attempts',[ATTEMPT_HEADERS,...attempts]);
  writeGrid(center,'Games',[['Game ID','Game','Created at','PDF URL','Game sheet','Last synced','Missing subjects'],...games]);
  for (const title of ['Player subjects',...SUBJECT_TABS]) {
  // Live subject views recalculate from All attempts, including when no games remain.
  const existingView = center.getSheetByName(title);
  if (title !== 'Player subjects' && existingView && existingView.getRange(2,1,1,1).getFormula().includes('LET(source,')) continue;
  const selected=title==='Player subjects' ? summary : summary.filter(g=>g.subject===title);
  const grid=writeGrid(center,title,[SUMMARY_HEADERS,...selected.map(g=>[
    g.id,g.name,g.subject,g.buzzes,g.correct,g.wrong,'',g.known,g.interrupts,'',g.icorrect,'',g.unknown,g.games.size])]);
  if(selected.length) {
    for(const [col,make] of [[7,r=>`=IF(D${r}=0,"",E${r}/D${r})`],[10,r=>`=IF(H${r}=0,"",I${r}/H${r})`],[12,r=>`=IF(I${r}=0,"",K${r}/I${r})`]]) {
      grid.getRange(2,col,selected.length,1).setFormulas(selected.map((_,i)=>[make(i+2)])).setNumberFormat('0.0%');
    }
  }
  }
  return {games:games.length,buzzes,center_url:center.getUrl()};
}
