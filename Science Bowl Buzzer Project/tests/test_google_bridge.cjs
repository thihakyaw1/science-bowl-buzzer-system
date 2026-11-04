const fs=require('fs'),vm=require('vm'),assert=require('assert');
const books=new Map(),folderFiles=[];
class Sheet {
  constructor(){this.rows=[];this.formulas={};}
  getLastRow(){return this.rows.length;} getLastColumn(){return this.rows[0]?.length||0;}
  getMaxRows(){return 1000;} getMaxColumns(){return 26;}
  setFrozenRows(){} setRowHeight(){} setColumnWidths(){} setColumnWidth(){}
  getDataRange(){return {getValues:()=>this.rows};}
  getRange(row,col,height,width){const sheet=this; return {
    getFormula(){return '';},
    setValues(values){values.forEach((r,i)=>{sheet.rows[row-1+i]??=[];r.forEach((v,j)=>sheet.rows[row-1+i][col-1+j]=v);});return this;},
    clearContent(){sheet.rows.splice(row-1,height);return this;},
    setFormulas(values){sheet.formulas[col]=values;return this;},
    setNumberFormat(){return this;},setBackground(){return this;},setFontWeight(){return this;},setWrap(){return this;}
  };}
}
class Book {
  constructor(id,name){this.id=id;this.name=name;this.sheets=new Map();books.set(id,this);}
  getId(){return this.id;} getName(){return this.name;}
  getUrl(){return 'https://docs.google.com/spreadsheets/d/'+this.id;}
  getSheetByName(name){return this.sheets.get(name);}
  insertSheet(name){const s=new Sheet();this.sheets.set(name,s);return s;}
}
const iterator=items=>{let i=0;return{hasNext:()=>i<items.length,next:()=>items[i++]};};
const center=new Book('YOUR_DATA_CENTER_SPREADSHEET_ID','center');
const folder={getFilesByName:n=>iterator(folderFiles.filter(f=>f.name===n)),getFilesByType:()=>iterator(folderFiles)};
const context=vm.createContext({SpreadsheetApp:{openById:id=>books.get(id),create:n=>new Book('new'+books.size,n),flush(){}},
  DriveApp:{getFolderById:()=>folder,getFileById:id=>({moveTo:()=>folderFiles.push(books.get(id))})},MimeType:{GOOGLE_SHEETS:'sheets'}});
vm.runInContext(fs.readFileSync('scripts/google/Code.gs','utf8'),context);
const game={game_key:'abc-123:1',name:'Test',created_at:'2026-01-01',pdf_url:'https://example.test/set.pdf',missing_subjects:[],
  questions:[{question_number:1,subject:'Biology',final_result:'Correct'}],
  attempts:[true,false,null].map((interrupt,i)=>({attempt_key:'abc-123:1:'+i,question_number:1,subject:'Biology',
    player_id:i+1,person_id:'stable-player',player_name:'Test Person',team:'A',result:i===1?'Wrong':'Correct',
    interrupt,correct:i!==1,elapsed_ms:100,created_at:'2026-01-01'}))};
context.game=game;
vm.runInContext('syncGame(game);syncGame(game)',context);
assert.equal(folderFiles.length,1,'Retry must update the same game');
assert.equal(center.getSheetByName('All attempts').rows.length,4,'No duplicate attempts');
const summary=center.getSheetByName('Player subjects'),all=summary.rows.find(r=>r[2]==='ALL');
assert.deepEqual(Array.from(all.slice(3,6)),[3,2,1]);
assert.equal(all[7],2,'Unknown timing excluded from denominator');
assert.equal(all[8],1);assert.equal(all[10],1);assert.equal(all[12],1);assert.equal(all[13],1);
assert.equal(summary.formulas[7][0][0],'=IF(D2=0,"",E2/D2)');
assert.equal(summary.formulas[10][0][0],'=IF(H2=0,"",I2/H2)');
assert.equal(summary.formulas[12][0][0],'=IF(I2=0,"",K2/I2)');
game.attempts.pop();vm.runInContext('syncGame(game)',context);
assert.equal(center.getSheetByName('All attempts').rows.length,3,'Removed attempts must not remain');
assert.equal(vm.runInContext('text("=IMPORTXML(x)")',context),"'=IMPORTXML(x)");
console.log('PASS Google bridge: retries, all attempts, statistics, unknown timing, stale rows, literal text');
game.attempts[0].subject='Astronomy';game.attempts[1].subject='Earth Science';
vm.runInContext('syncGame(game)',context);
const earth=center.getSheetByName('Earth and Space').rows;
assert.equal(earth.length,2);assert.equal(earth[1][3],2);assert.equal(earth[1][13],1);
assert.equal(center.getSheetByName('Biology').rows.length,1);
assert.equal(center.getSheetByName('All attempts').rows[0].includes('Team'),false);
assert.equal(vm.runInContext('subjectGroup("General Science")',context),'Energy');
assert.equal(vm.runInContext('subjectGroup("Earth And Space Science")',context),'Earth and Space');
console.log('PASS subject tabs: combined counts, unique games, stale-row removal, no Team column');
