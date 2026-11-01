"""Read-only UnityFS audit using seekable decompressed blocks, never whole bundles."""
import io, sys, json, re, bisect, collections, gc, argparse, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from UnityPy.streams import EndianBinaryReader as Reader
from UnityPy.helpers.CompressionHelper import decompress_lz4, decompress_lzma
from UnityPy.files.SerializedFile import SerializedFile
from common import BUNDLES, GAME, WORK

def unpack(data, size, flags):
    mode = flags & 63
    if mode == 0: result = data
    elif mode in (2,3): result = decompress_lz4(data, size)
    elif mode == 1: result = decompress_lzma(data)
    else: raise ValueError(('compression',mode))
    if len(result) != size: raise ValueError(('block size',len(result),size))
    return result

class Bundle:
    def __init__(self,path):
        self.file=open(path,'rb'); r=Reader(self.file)
        assert r.read_string_to_null()=='UnityFS'
        self.version=r.read_u_int(); self.player=r.read_string_to_null(); self.engine=r.read_string_to_null()
        size=r.read_long(); cs=r.read_u_int(); us=r.read_u_int(); flags=r.read_u_int()
        if self.version>=7: r.align_stream(16)
        start=r.Position
        if flags & 128: r.Position=size-cs
        info=Reader(unpack(r.read_bytes(cs),us,flags))
        if flags & 128: r.Position=start
        if flags & 512: r.align_stream(16)
        data_start=r.Position
        info.read_bytes(16); count=info.read_int()
        self.blocks=[]; self.starts=[]; co=data_start; uo=0
        for _ in range(count):
            u=info.read_u_int(); c=info.read_u_int(); f=info.read_u_short()
            self.starts.append(uo); self.blocks.append((co,c,u,f)); co+=c; uo+=u
        self.nodes=[]
        for _ in range(info.read_int()):
            off=info.read_long(); sz=info.read_long(); fl=info.read_u_int(); name=info.read_string_to_null()
            self.nodes.append(dict(offset=off,size=sz,flags=fl,name=name))
        self.cache=collections.OrderedDict(); self.total=uo
    def read(self,offset,size):
        result=[]
        while size>0:
            i=bisect.bisect_right(self.starts,offset)-1
            if i not in self.cache:
                co,c,u,f=self.blocks[i]; self.file.seek(co)
                self.cache[i]=unpack(self.file.read(c),u,f)
                while len(self.cache)>4: self.cache.popitem(last=False)
            block=self.cache[i]; self.cache.move_to_end(i)
            local=offset-self.starts[i]; n=min(size,len(block)-local)
            if n<=0: raise EOFError(offset)
            result.append(block[local:local+n]); offset+=n; size-=n
        return b''.join(result)
    def close(self): self.file.close(); self.cache.clear()

class Slice(io.RawIOBase):
    def __init__(self,bundle,node): self.bundle=bundle; self.node=node; self.pos=0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.node['size']+offset
        return self.pos
    def read(self,size=-1):
        if size<0: size=self.node['size']-self.pos
        size=min(size,self.node['size']-self.pos)
        data=self.bundle.read(self.node['offset']+self.pos,max(0,size)); self.pos+=len(data); return data

def strings(value,path=''):
    if isinstance(value,str):
        if value: yield path,value
    elif isinstance(value,dict):
        for k,v in value.items(): yield from strings(v,path+'/'+str(k))
    elif isinstance(value,(list,tuple)):
        for i,v in enumerate(value): yield from strings(v,path+'/'+str(i))

def scan_serial(sf, result, cab):
    for obj in sf.objects.values():
        kind=obj.type.name; result['types'][kind]+=1
        if kind=='TextAsset':
            obj.reset(); name=obj.reader.read_aligned_string(); size=obj.reader.read_int()
            result['binary_assets'].append([cab,obj.path_id,kind,name,size])
            # TPS scripts already have a dedicated, complete segment audit.
            # Search binary payloads in bounded chunks; retain meaningful phrases only.
            phrases=set(); tail=b''; remaining=size; small=[]
            while remaining:
                chunk=obj.reader.read_bytes(min(remaining,1024*1024)); remaining-=len(chunk)
                if not chunk: raise EOFError(name)
                data=tail+chunk
                if size<=65536: small.append(chunk)
                phrases.update(x.decode('ascii') for x in re.findall(rb'\b[A-Za-z]{2,}(?: [A-Za-z]{2,}){2,}\b',data))
                tail=data[-1024:]
            for phrase in sorted(phrases): result['strings'].append([cab,obj.path_id,kind,'/m_Script/phrase',phrase])
            if small:
                try:
                    text=b''.join(small).decode('utf-8')
                    if '\x00' not in text: result['strings'].append([cab,obj.path_id,kind,'/m_Script/text',text])
                except UnicodeDecodeError: pass
            continue
        # Typed strings (including TMP/UI/MonoBehaviour), no blind byte decoding of images.
        if kind in ('Texture2D','Mesh','AudioClip','VideoClip','Font','Shader'):
            # Name only; bodies are binary, shaders are code.
            obj.reset(); name=obj.reader.read_aligned_string()
            result['binary_assets'].append([cab,obj.path_id,kind,name,obj.byte_size])
            continue
        try:
            tree=obj.read_typetree()
        except Exception as e:
            # Player builds strip MonoBehaviour schemas. Still enumerate every
            # 4-byte-aligned Unity string candidate in the complete object bytes.
            if kind=='MonoBehaviour':
                raw=obj.get_raw_data(); found=0
                for off in range(0,len(raw)-4,4):
                    length=struct.unpack_from('<i',raw,off)[0]
                    if not 2<=length<=len(raw)-off-4: continue
                    payload=raw[off+4:off+4+length]
                    if b'\x00' in payload: continue
                    try: value=payload.decode('utf-8')
                    except UnicodeDecodeError: continue
                    if any(ord(c)<32 and c not in '\t\n\r' for c in value): continue
                    if not any(c.isalpha() for c in value): continue
                    result['strings'].append([cab,obj.path_id,kind,f'/raw-string@{off}',value]); found+=1
                result['fallback'].append([cab,obj.path_id,len(raw),found,str(e)])
            else: result['errors'].append([cab,obj.path_id,kind,str(e)])
            continue
        for field,value in strings(tree):
            result['strings'].append([cab,obj.path_id,kind,field,value])

def scan(path):
    result={'file':str(path),'types':collections.Counter(),'strings':[],'binary_assets':[],'errors':[],'fallback':[],'nodes':[]}
    with open(path,'rb') as probe: is_bundle=probe.read(7)==b'UnityFS'
    if is_bundle:
        b=Bundle(path); result['nodes']=b.nodes
        try:
            for node in b.nodes:
                if node['flags'] & 4:
                    sf=SerializedFile(Reader(Slice(b,node)),name=node['name'])
                    scan_serial(sf,result,node['name']); del sf; gc.collect()
        finally: b.close()
    else:
        with open(path,'rb') as f:
            sf=SerializedFile(Reader(f),name=path.name); scan_serial(sf,result,path.name)
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--one'); ap.add_argument('--all',action='store_true'); ap.add_argument('--force',action='store_true'); args=ap.parse_args()
    out=WORK/'audit_complete_20261101_v2'; out.mkdir(exist_ok=True)
    if args.one: paths=[Path(args.one)]
    elif args.all:
        paths=sorted(BUNDLES.glob('*.bundle'))
        paths += [p for p in sorted((GAME/'GK12_Data').rglob('*')) if p.is_file() and (p.suffix in ('.assets','.unity3d') or p.name=='globalgamemanagers' or re.fullmatch(r'level\d+',p.name))]
    else:
        inventory=json.loads((WORK/'qa_global_20261101_inventory.json').read_text(encoding='utf-8'))
        paths=[BUNDLES/e['file'] for e in inventory if e['category']=='не покрыто' and 'kinds' not in e]
    for i,p in enumerate(paths):
        dest=out/(p.name+'.json')
        if dest.exists() and not args.force: print('CACHED',p.name,flush=True); continue
        print('START',i+1,len(paths),p.name,flush=True)
        result=scan(p)
        dest.write_text(json.dumps(result,ensure_ascii=True,indent=1),encoding='utf-8')
        print('DONE',p.name,dict(result['types']),'strings',len(result['strings']),'errors',len(result['errors']),flush=True)
        del result; gc.collect()

if __name__=='__main__': main()
