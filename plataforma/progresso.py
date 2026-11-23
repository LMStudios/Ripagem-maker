"""Progresso por fase; downloads sem tamanho conhecido nunca exibem percentual."""
import time


def phase(job,kind,label,indeterminate=True):
    job.pct=0.0
    job.progress={'fase':kind,'rotulo':label,'indeterminado':indeterminate}


class DownloadProgress:
    def __init__(self,job,label,headers):
        self.job,self.label=job,label
        try:self.total=int(headers.get('Content-Length','0'))
        except (ValueError,TypeError):self.total=0
        if self.total<=0 or headers.get('Content-Encoding','identity').lower() not in ('','identity') or 'chunked' in headers.get('Transfer-Encoding','').lower():self.total=0
        self.received=0;self.last=0;self.started=time.monotonic()
        self.update(force=True)

    def add(self,size):
        self.received+=size
        # Um total excedido não é confiável (p.ex. resposta intermediária de CDN).
        if self.total and self.received>self.total:self.total=0
        self.update()

    def update(self,force=False):
        now=time.monotonic()
        if not force and now-self.last<.5:return
        self.last=now
        p={'fase':'download','rotulo':self.label,'indeterminado':not bool(self.total),
           'bytes_recebidos':self.received,'bytes_total':self.total or None}
        self.job.progress=p
        self.job.pct=min(.999,self.received/self.total) if self.total else 0.0
        mb=self.received/1048576
        self.job.step=f'Baixando {self.label} · {mb:.2f} MB'
        if self.total:self.job.step+=f' de {self.total/1048576:.2f} MB'
        else:self.job.step+=' · tamanho total não informado'
