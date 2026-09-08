"""Chat backup and image retention, restricted to app-owned names."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time

class Storage:
    def __init__(self, data):
        self.data = data
        self.local = data / 'images'
    def config(self):
        try: c = json.loads((self.data/'backup-config.json').read_text())
        except (OSError, ValueError): c = {}
        return {'folder':'','image_storage':'backup','retention_days':0,'max_image_gb':5,**c}
    def configure(self, body):
        c = self.config()
        for key in ['folder','image_storage','retention_days','max_image_gb']:
            if key in body: c[key] = body[key]
        if c['image_storage'] not in ['backup','local']: raise ValueError('Invalid image storage mode.')
        c['retention_days'] = int(c['retention_days'])
        if not 0 <= c['retention_days'] <= 3650: raise ValueError('Retention must be 0–3650 days.')
        c['max_image_gb']=float(c['max_image_gb'])
        if not 0 <= c['max_image_gb'] <= 1000: raise ValueError('Image limit must be 0–1000 GB.')
        if c['folder']:
            folder = Path(c['folder']).expanduser()
            if not folder.is_absolute(): raise ValueError('Use an absolute folder path.')
            folder.mkdir(parents=True,exist_ok=True)
            probe=folder/('openvino-check-'+secrets.token_hex(8)+'.tmp')
            try: probe.write_text('test')
            finally: probe.unlink(missing_ok=True)
            c['folder']=str(folder.resolve())
        self.atomic(self.data/'backup-config.json',c)
        return c
    def folder(self):
        value=self.config()['folder']
        if not value: raise ValueError('Set a backup folder before attaching images, or enable local image storage.')
        return Path(value)
    def image_dir(self):
        p=self.folder()/'openvino-chat-images' if self.config()['image_storage']=='backup' else self.local
        p.mkdir(parents=True,exist_ok=True)
        return p
    def image_path(self, name):
        if not isinstance(name,str) or not re.fullmatch(r'[a-f0-9]{32}\.jpg',name): raise ValueError('Invalid image reference.')
        return self.folder()/'openvino-chat-images'/name
    def tombstones(self):
        try: return json.loads((self.data/'purged-images.json').read_text())
        except (OSError,ValueError): return []
    def migrate_images(self):
        if self.config()['image_storage']!='backup': return 0
        destination=self.image_dir();count=0
        for old in self.local.glob('*.jpg'):
            if not re.fullmatch(r'[a-f0-9]{32}\.jpg',old.name):continue
            target=destination/old.name
            if not target.exists(): shutil.copy2(old,target)
            if hashlib.sha256(old.read_bytes()).digest()!=hashlib.sha256(target.read_bytes()).digest():
                raise ValueError('Image copy verification failed; local original preserved.')
            old.unlink();count+=1
        return count
    def purge(self, force=False):
        days=self.config()['retention_days']
        max_bytes=int(self.config()['max_image_gb']*1024**3)
        cutoff=time.time()-days*86400
        removed=set(self.tombstones())
        dirs=[self.local]
        if self.config()['folder']:dirs.append(Path(self.config()['folder'])/'openvino-chat-images')
        for directory in dirs:
            for p in directory.glob('*.jpg'):
                if re.fullmatch(r'[a-f0-9]{32}\.jpg',p.name) and (force or (days and p.stat().st_mtime<cutoff)):
                    p.unlink();removed.add(p.name)
        # Apply the total size ceiling, removing oldest app-owned images first.
        files=[p for directory in dirs for p in directory.glob('*.jpg') if re.fullmatch(r'[a-f0-9]{32}\.jpg',p.name)]
        total=sum(p.stat().st_size for p in files)
        if max_bytes:
            for p in sorted(files,key=lambda p:p.stat().st_mtime):
                if total<=max_bytes:break
                size=p.stat().st_size;p.unlink();total-=size;removed.add(p.name)
        self.atomic(self.data/'purged-images.json',sorted(removed))
        return sorted(removed)
    @staticmethod
    def atomic(path, value):
        path.parent.mkdir(parents=True,exist_ok=True)
        content=json.dumps(value,ensure_ascii=False,indent=2)
        try:
            if path.read_text(encoding='utf-8') == content: return
        except (OSError, UnicodeError): pass
        temp=path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
        try:
            for attempt in range(6):
                try:
                    temp.write_text(content,encoding='utf-8')
                    os.replace(temp,path)
                    return
                except PermissionError as e:
                    if attempt == 5:
                        raise PermissionError('Cannot save to '+str(path.parent)+'. Check folder write access or OneDrive sync status, then retry saving.') from e
                    time.sleep(0.15 * 2**attempt)
        finally:
            try: temp.unlink(missing_ok=True)
            except OSError: pass
    def save(self,body):
        if not isinstance(body.get('chats'),list) or not isinstance(body.get('prefs'),dict):raise ValueError('Invalid backup.')
        folder=self.folder();dest=folder/'chats';dest.mkdir(parents=True,exist_ok=True)
        images=folder/'openvino-chat-images';images.mkdir(exist_ok=True)
        removed=set(self.purge())
        ids=[]
        for original in body['chats']:
            chat=json.loads(json.dumps(original))
            if not isinstance(chat.get('id'),str) or not isinstance(chat.get('messages'),list):raise ValueError('Invalid conversation.')
            for m in chat['messages']:
                keep=[]
                for im in m.get('images',[]):
                    source=self.image_path(im['id'])
                    if im['id'] in removed or not source.exists():continue
                    target=images/im['id']
                    if source.resolve()!=target.resolve() and not target.exists():shutil.copy2(source,target)
                    keep.append(im)
                if m.get('images') and not keep:m['imagesPurged']=True
                if 'images' in m:m['images']=keep
            name=hashlib.sha256(chat['id'].encode()).hexdigest()+'.json'
            self.atomic(dest/name,chat);ids.append(name)
        self.atomic(folder/'chat-index.json',{'version':2,'files':ids,'active':body.get('active'),'prefs':body['prefs']})
        self.migrate_images()
        return {'saved':True,'conversations':len(ids),'purged':list(removed)}
    def restore(self,folder):
        folder=Path(folder)
        if not folder.is_absolute():raise ValueError('Use an absolute folder path.')
        index = json.loads((folder/'chat-index.json').read_text(encoding='utf-8')) if (folder/'chat-index.json').is_file() else {}
        chats=[]
        for file in sorted((folder/'chats').glob('*.json')):
            if file.stat().st_size>20000000:raise ValueError('Conversation file too large.')
            chats.append(json.loads(file.read_text(encoding='utf-8')))
        saved={'chats':chats,'prefs':index.get('prefs',{}),'active':index.get('active')}
        if not isinstance(saved.get('chats'),list) or not isinstance(saved.get('prefs'),dict):raise ValueError('Invalid backup.')
        for chat in saved['chats']:
            if not isinstance(chat.get('id'),str) or not isinstance(chat.get('title'),str) or not isinstance(chat.get('messages'),list):raise ValueError('Invalid chat.')
            for m in chat['messages']:
                if m.get('role') not in ['user','assistant'] or not isinstance(m.get('content'),str):raise ValueError('Invalid message.')
                for im in m.get('images',[]):
                    if not re.fullmatch(r'[a-f0-9]{32}\.jpg',im.get('id','')):raise ValueError('Invalid image.')
        # Read images directly from the restored folder; do not create a local duplicate.
        # Reading a datastore does not change the selected folder.
        return saved
