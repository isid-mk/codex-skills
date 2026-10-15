"""Remove formula stage bars and case-tab colors without moving evidence drawings."""
import argparse,copy,json,pathlib,re,zipfile,posixpath,math
from lxml import etree as E

S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
q=lambda name:'{'+S+'}'+name
D='http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
def resolve(base,target):return target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(base),target))
def apply(source,destination,catalog):
 source=pathlib.Path(source);destination=pathlib.Path(destination)
 if source.resolve()==destination.resolve():raise ValueError('Use a separate output file')
 formulas={'ケースNo'+str(c['caseNo']) for c in catalog['cases'] if c['category']=='数式項目'}
 with zipfile.ZipFile(source) as z:
  book=E.fromstring(z.read('xl/workbook.xml'));rels=E.fromstring(z.read('xl/_rels/workbook.xml.rels'))
  paths={r.get('Id'):('xl/'+r.get('Target').lstrip('/') if not r.get('Target').startswith('/') else r.get('Target').lstrip('/')) for r in rels}
  strings=[]
  if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(t.text or '' for t in s.findall(q('t'))+s.findall(q('r')+'/'+q('t'))) for s in E.fromstring(z.read('xl/sharedStrings.xml'))]
  styles=E.fromstring(z.read('xl/styles.xml'));xfs=styles.find(q('cellXfs'));style_map={};modified={};report={'formulaSheets':[],'removedStageBars':0,'removedTabColors':0,'removedPlaceholders':0,'formulaImageStartRow':6}
  def text(c):
   if c.get('t')=='s':return strings[int(c.find(q('v')).text)]
   if c.get('t')=='inlineStr':return ''.join(c.find(q('is')).itertext())
   v=c.find(q('v'));return v.text if v is not None else ''
  def white_style(old):
   if old not in style_map:
    new=copy.deepcopy(xfs[old]);new.set('fillId','0');new.set('applyFill','0');xfs.append(new);style_map[old]=len(xfs)-1
   return style_map[old]
  for sheet in book.find(q('sheets')):
   name=sheet.get('name');sheet_path=paths[sheet.get('{'+R+'}id')]
   root=E.fromstring(z.read(sheet_path));changed=False
   prop=root.find(q('sheetPr'));color=prop.find(q('tabColor')) if prop is not None else None
   if color is not None and name.startswith('ケースNo'):prop.remove(color);changed=True;report['removedTabColors']+=1
   for c in root.findall('.//'+q('c')):
    if text(c).strip() in ['（ここにエビデンス添付）','(ここにエビデンス添付)']:
     for child in list(c):c.remove(child)
     c.attrib.pop('t',None);changed=True;report['removedPlaceholders']+=1
   if name in formulas:
    report['formulaSheets'].append(name)
    data=root.find(q('sheetData'));rows={int(r.get('r')):r for r in data};starts=[]
    for row in data:
     values={re.sub(r'\d+$','',c.get('r')):text(c) for c in row}
     if values.get('E')=='数式項目' and values.get('A')==name.replace('ケースNo',''):starts.append(int(row.get('r'))-3)
    if not starts:raise ValueError('Formula case information not found: '+name)
    drawing=None;drawing_path=None;node=root.find(q('drawing'))
    if node is not None:
     sheet_rels=E.fromstring(z.read(posixpath.dirname(sheet_path)+'/_rels/'+posixpath.basename(sheet_path)+'.rels'))
     relation=next(r for r in sheet_rels if r.get('Id')==node.get('{'+R+'}id'));drawing_path=resolve(sheet_path,relation.get('Target'));drawing=E.fromstring(z.read(drawing_path))
    anchors=list(drawing) if drawing is not None else []
    original_positions={id(a):int(a.find('{'+D+'}from/{'+D+'}row').text)+1 for a in anchors}
    data.clear();merges=root.find(q('mergeCells'));old_merges=copy.deepcopy(merges);merges.clear();next_start=1
    default=float(root.find(q('sheetFormatPr')).get('defaultRowHeight','15'))
    for index,start in enumerate(starts):
     upper=starts[index+1] if index+1<len(starts) else 10**9
     for old in range(start,start+4):
      row=copy.deepcopy(rows[old]);new=next_start+old-start;row.set('r',str(new))
      for c in row:c.set('r',re.sub(r'\d+$',str(new),c.get('r')))
      data.append(row)
     for merge in old_merges:
      first=int(re.search(r'\d+',merge.get('ref')).group())
      if start<=first<start+4:
       new=copy.deepcopy(merge);new.set('ref',re.sub(r'\d+',lambda m:str(int(m.group())+next_start-start),merge.get('ref')));merges.append(new)
     cursor=next_start+5
     for anchor in [a for a in anchors if start<=original_positions[id(a)]<upper]:
      if E.QName(anchor).localname!='oneCellAnchor':raise ValueError('Formula anchor requires an explicit layout conversion')
      anchor.find('{'+D+'}from/{'+D+'}row').text=str(cursor-1);anchor.find('{'+D+'}from/{'+D+'}rowOff').text='0';anchor.find('{'+D+'}from/{'+D+'}col').text='0';anchor.find('{'+D+'}from/{'+D+'}colOff').text='0'
      height=int(anchor.find('{'+D+'}ext').get('cy'))/9525;count=math.ceil(height/(default*4/3))+2
      for n in range(cursor,cursor+count):E.SubElement(data,q('row'),r=str(n))
      cursor+=count
     end=max(next_start+5,cursor-1);next_start=end+1
    merges.set('count',str(len(merges)));root.find(q('dimension')).set('ref','A1:N'+str(next_start-1));changed=True
    if drawing_path:modified[drawing_path]=E.tostring(drawing,encoding='UTF-8',xml_declaration=True,standalone=True)
   if changed:modified[sheet_path]=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
  if style_map:
   xfs.set('count',str(len(xfs)));modified['xl/styles.xml']=E.tostring(styles,encoding='UTF-8',xml_declaration=True,standalone=True)
  destination.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as out:
   for name in z.namelist():out.writestr(name,modified.get(name,z.read(name)))
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination');p.add_argument('--catalog',required=True);a=p.parse_args()
 catalog=json.loads(pathlib.Path(a.catalog).read_text(encoding='utf-8-sig'))
 print(json.dumps(apply(a.source,a.destination,catalog),ensure_ascii=False))
