import struct

OPS = {
0x04:'NextFrame',0x05:'PrevFrame',0x06:'Play',0x07:'Stop',0x09:'StopSounds',
0x0A:'Add',0x0B:'Subtract',0x0C:'Multiply',0x0D:'Divide',0x0E:'Equals',0x0F:'Less',0x10:'And',0x11:'Or',
0x12:'Not',0x13:'StringEquals',0x14:'StringLength',0x15:'StringExtract',
0x17:'Pop',0x18:'ToInteger',0x1C:'GetVariable',0x1D:'SetVariable',0x20:'SetTarget2',
0x21:'StringAdd',0x22:'GetProperty',0x23:'SetProperty',0x24:'CloneSprite',0x25:'RemoveSprite',
0x26:'Trace',0x27:'StartDrag',0x28:'EndDrag',0x29:'StringLess',0x2A:'Throw',0x2B:'CastOp',0x2C:'ImplementsOp',
0x30:'RandomNumber',0x31:'MBStringLength',0x32:'CharToAscii',0x33:'AsciiToChar',0x34:'GetTime',
0x35:'MBStringExtract',0x36:'MBCharToAscii',0x37:'MBAsciiToChar',0x3A:'Delete',0x3B:'Delete2',
0x3C:'DefineLocal',0x3D:'CallFunction',0x3E:'Return',0x3F:'Modulo',0x40:'NewObject',0x41:'DefineLocal2',
0x42:'InitArray',0x43:'InitObject',0x44:'TypeOf',0x45:'TargetPath',0x46:'Enumerate',0x47:'Add2',
0x48:'Less2',0x49:'Equals2',0x4A:'ToNumber',0x4B:'ToString',0x4C:'PushDuplicate',0x4D:'StackSwap',
0x4E:'GetMember',0x4F:'SetMember',0x50:'Increment',0x51:'Decrement',0x52:'CallMethod',0x53:'NewMethod',
0x54:'InstanceOf',0x55:'Enumerate2',0x60:'BitAnd',0x61:'BitOr',0x62:'BitXor',0x63:'BitLShift',
0x64:'BitRShift',0x65:'BitURShift',0x66:'StrictEquals',0x67:'Greater',0x68:'StringGreater',
0x69:'Extends',0x81:'GotoFrame',0x83:'GetURL',0x87:'StoreRegister',0x88:'ConstantPool',0x8A:'WaitForFrame',
0x8B:'SetTarget',0x8C:'GotoLabel',0x8D:'WaitForFrame2',0x8E:'DefineFunction2',0x8F:'Try',0x94:'With',
0x96:'Push',0x99:'Jump',0x9A:'GetURL2',0x9B:'DefineFunction',0x9D:'If',0x9E:'Call',0x9F:'GotoFrame2',
}

def dis(code, pool=None, indent=0):
    if pool is None: pool=[]
    out=[]; p=0
    while p < len(code):
        start=p; op=code[p]; p+=1
        nm=OPS.get(op, 'op_%02x'%op)
        extra=''
        if op==0x96:
            types=[]
            while p < len(code):
                t=code[p]; p+=1
                if t==0:
                    l=struct.unpack('<I',code[p:p+4])[0]; p+=4
                    types.append('str:%r'%code[p:p+l].decode('latin1')); p+=l
                elif t==1:
                    v=struct.unpack('<f',code[p:p+4])[0]; p+=4; types.append('f(%g)'%v)
                elif t==2: types.append('null')
                elif t==3: types.append('undefined')
                elif t==4: types.append('reg%d'%code[p]); p+=1
                elif t==5: types.append('bool(%s)'%bool(code[p])); p+=1
                elif t==6: v=struct.unpack('<d',code[p:p+8])[0]; p+=8; types.append('num(%g)'%v)
                elif t==7: v=struct.unpack('<i',code[p:p+4])[0]; p+=4; types.append('int(%d)'%v)
                elif t==8:
                    i=code[p]; p+=1
                    types.append('c%d=%r'%(i, pool[i] if i<len(pool) else '?'))
                elif t==9:
                    i=struct.unpack('<H',code[p:p+2])[0]; p+=2
                    types.append('c%d=%r'%(i, pool[i] if i<len(pool) else '?'))
                else:
                    types.append('<?t%d>'%t); break
                if p>=len(code) or not (code[p] & 0x80): break
            out.append(' '*indent+'%5d: Push  '%start + ', '.join(types))
            continue
        if op in (0x99,0x9d,0x8a,0x9b,0x9e,0x81,0x83):
            v=struct.unpack('<h',code[p:p+2])[0]; p+=2; extra=str(v)
        elif op in (0x87,0x94):
            extra=str(code[p]); p+=1
        elif op==0x88:
            cnt=struct.unpack('<H',code[p:p+2])[0]; p+=2
            extra='count=%d'%cnt
            for i in range(cnt):
                l=code[p]; p+=1
                if l==0:
                    l=struct.unpack('<I',code[p:p+4])[0]; p+=4
                s=code[p:p+l].decode('latin1'); p+=l
                pool.append(s)
                extra+='\n'+' '*indent+'        [%d] %r'%(i,s)
        elif op==0x8e:
            nlen=code[p]; p+=1; nlen2=code[p]; p+=1
            nparams=struct.unpack('<H',code[p:p+2])[0]; p+=2
            nregs=code[p]; p+=1
            flags=struct.unpack('<H',code[p:p+2])[0]; p+=2
            cs=struct.unpack('<H',code[p:p+2])[0]; p+=2
            out.append(' '*indent+'%5d: DefineFunction2 nameLen=%d(%s) nparams=%d nregs=%d flags=0x%04x codeSize=%d'%(start,nlen,nlen2,nparams,nregs,flags,cs))
            out.extend(dis(code[p:p+cs], pool, indent+8)); p+=cs; continue
        elif op==0x8c:
            i=code.index(0,p); s=code[p:i].decode('latin1'); extra=repr(s); p=i+1
        elif op in (0x9f,):
            extra='flags=0x%02x'%code[p]; p+=1
        out.append(' '*indent+'%5d: %s  %s'%(start,nm,extra))
    return out

def get_tags(data):
    p=8
    nbits=data[p]>>3
    p+= (5+nbits*4+7)//8 + 4
    tags=[]
    while p<len(data)-1:
        th=struct.unpack('<H',data[p:p+2])[0]; code=th>>6; ln=th&0x3f; hdr=2
        if ln==0x3f: ln=struct.unpack('<I',data[p+2:p+6])[0]; hdr=6
        if code==0: break
        tags.append((code,p,hdr,ln,p+hdr)); p+=hdr+ln
    return tags

def dumps(path, off, label):
    d=open(path,'rb').read()
    for code,o,hdr,ln,do in get_tags(d):
        if o==off:
            print("#"*70); print(label,"code=%d off=%d len=%d"%(code,o,ln))
            for l in dis(d[do:do+ln]): print(l)
            return
    print(label,"MISSING",off)
