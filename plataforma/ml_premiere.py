"""Sequência editável ML + body em FCP7 XML, referenciando as fontes locais."""
import math
import re
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET


def export(spec,destination,name,library):
    from . import ml_core as M
    segments=[]
    for key in ('lead','body'):
        part=spec[key];meta=M.read_meta(part['video'])
        if not meta:raise ValueError('Vídeo de origem não encontrado.')
        info=meta['probe'];src=library(part['video'])/meta['arquivo']
        if not src.is_file():raise ValueError('Mídia de origem ausente para o XML.')
        start=float(part.get('inicio',0));end=float(part.get('fim') or info['duracao'])
        if not all(math.isfinite(v) for v in (start,end)) or start<0 or end>info['duracao']+.04 or end-start<.5:raise ValueError('Trecho fora da duração da fonte.')
        segments.append((key,src,info,start,end))
    target=segments[1][2];fps=float(target['fps']);root=ET.Element('xmeml',version='4');seq=ET.SubElement(root,'sequence',id='ml-'+uuid.uuid4().hex[:10])
    def val(p,k,v):ET.SubElement(p,k).text=str(v)
    def rate(p,f):
        r=ET.SubElement(p,'rate');val(r,'timebase',round(f));val(r,'ntsc','TRUE' if abs(f-round(f))>.01 else 'FALSE')
    val(seq,'name','DR ML + Body · '+name);rate(seq,fps)
    durations=[round((end-start)*fps) for _,_,_,start,end in segments];val(seq,'duration',sum(durations))
    media=ET.SubElement(seq,'media');video=ET.SubElement(media,'video');fmt=ET.SubElement(ET.SubElement(video,'format'),'samplecharacteristics');rate(fmt,fps)
    for k,v in [('width',target['largura']),('height',target['altura']),('pixelaspectratio','square'),('fielddominance','none')]:val(fmt,k,v)
    vt=ET.SubElement(video,'track');audio=ET.SubElement(media,'audio');at=ET.SubElement(audio,'track');offset=0
    for i,((key,src,info,start,end),duration) in enumerate(zip(segments,durations)):
        sourcefps=float(info['fps']);kinds=['video']+(['audio'] if info['tem_audio'] else [])
        for kind in kinds:
            track=vt if kind=='video' else at;c=ET.SubElement(track,'clipitem',id=f'ml-{kind}-{i}')
            for k,v in [('name',('ML · ' if i==0 else 'BODY · ')+src.name),('enabled','TRUE'),('duration',round(info['duracao']*sourcefps)),('start',offset),('end',offset+duration),('in',round(start*sourcefps)),('out',round(end*sourcefps))]:val(c,k,v)
            rate(c,sourcefps)
            f=ET.SubElement(c,'file',id='source-'+str(i));val(f,'name',src.name);val(f,'pathurl',src.resolve().as_uri());val(f,'duration',round(info['duracao']*sourcefps));rate(f,sourcefps)
            fm=ET.SubElement(f,'media');sc=ET.SubElement(ET.SubElement(fm,'video'),'samplecharacteristics');rate(sc,sourcefps)
            for k,v in [('width',info['largura']),('height',info['altura']),('pixelaspectratio','square')]:val(sc,k,v)
            if info['tem_audio']:
                am=ET.SubElement(fm,'audio');val(am,'channelcount',info.get('channels') or 2);ac=ET.SubElement(am,'samplecharacteristics');val(ac,'samplerate',info.get('sample_rate') or 48000);val(ac,'depth',16)
            st=ET.SubElement(c,'sourcetrack');val(st,'mediatype',kind);val(st,'trackindex',1)
            for linked in kinds:
                link=ET.SubElement(c,'link');val(link,'linkclipref',f'ml-{linked}-{i}');val(link,'mediatype',linked);val(link,'trackindex',1);val(link,'clipindex',i+1)
        marker=ET.SubElement(seq,'marker');val(marker,'name','MICROLEAD' if i==0 else 'BODY');val(marker,'in',offset);val(marker,'out',offset+duration)
        offset+=duration
    from .nomes_arquivos import write_xml
    path=write_xml(root,destination,name,'Troca de ML')
    return path.name
