"""Fecha a margem de limpeza em todas as trilhas, sem lacunas artificiais."""
import copy

def windows(changes,fps):
    from . import montagem as MT
    result=[];previous=0
    for e in changes:
        left=MT.mute_start(e['a'],previous,fps)
        a=MT.shift(left,changes);b=e['start']
        if b>a:result.append((a,b))
        previous=e['b']
    return result

def position(frame,cuts):return frame-sum(max(0,min(frame,b)-a) for a,b in cuts if frame>a)

def kept(a,b,cuts):
    pieces=[(a,b)]
    for x,y in cuts:pieces=[p for lo,hi in pieces for p in ((lo,min(hi,x)),(max(lo,y),hi)) if p[1]>p[0]]
    return pieces

def expand(start,end,cuts):
    """Converte intervalo final em partes anteriores ao fechamento, sem perder quadros da mídia."""
    result=[];cursor=0;removed=0
    for a,b in cuts:
        lo=max(start,cursor-removed);hi=min(end,a-removed)
        if hi>lo:result.append((lo+removed,hi+removed,lo-start))
        cursor=b;removed+=b-a
    lo=max(start,cursor-removed)
    if end>lo:result.append((lo+removed,end+removed,lo-start))
    return result


def xml(sequence,cuts,fps):
    """Corta o mesmo intervalo de V1/V2/A1/A2/A3, trilha e marcadores."""
    if not cuts:return
    for track in sequence.findall('.//media/video/track')+sequence.findall('.//media/audio/track'):
        for clip in list(track.findall('clipitem')):
            a=int(clip.findtext('start'));b=int(clip.findtext('end'));ins=int(clip.findtext('in'));outs=int(clip.findtext('out'))
            parts=kept(a,b,cuts);index=list(track).index(clip);track.remove(clip)
            for n,(lo,hi) in enumerate(parts):
                c=copy.deepcopy(clip);c.set('id',clip.get('id')+'-fechado-'+str(n))
                for key,value in [('start',position(lo,cuts)),('end',position(hi,cuts)),('in',ins+round((lo-a)*(outs-ins)/(b-a))),('out',ins+round((hi-a)*(outs-ins)/(b-a)))]:c.find(key).text=str(value)
                track.insert(index+n,c)
    for marker in sequence.findall('marker'):
        for key in ('in','out'):
            node=marker.find(key)
            if node is not None:node.text=str(position(int(node.text),cuts))
    duration=sequence.find('duration');duration.text=str(position(int(duration.text),cuts))

def video_filter(filters,label,cuts,total,fps):
    pieces=kept(0,total,cuts)
    if not cuts:return label
    names=[f'closein{i}' for i in range(len(pieces))];filters.append(f'[{label}]split={len(names)}'+''.join('['+n+']' for n in names));outputs=[]
    for i,(a,b) in enumerate(pieces):
        name=f'closepart{i}';filters.append(f'[{names[i]}]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[{name}]');outputs.append('['+name+']')
    filters.append(''.join(outputs)+f'concat=n={len(outputs)}:v=1:a=0[vclosed]');return 'vclosed'
