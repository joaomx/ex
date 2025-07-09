# app.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Date, JSON, LargeBinary, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import pdfplumber

# ----------------------
# CONFIGURAÇÃO DO DB
# ----------------------
DB_FILE = 'empresas.db'
DB_URL = f'sqlite:///{DB_FILE}'
Base = declarative_base()

# ----------------------
# MODELAGEM
# ----------------------
def define_models():
    class Empresa(Base):
        __tablename__ = 'empresa'
        empresa_id = Column(Integer, primary_key=True, autoincrement=True)
        nome = Column(String, nullable=False)
        forma_juridica = Column(String, nullable=False)
        data_constituicao = Column(Date, nullable=False)
        eventos = relationship(
            'EventoEmpresa', back_populates='empresa', cascade='all, delete-orphan'
        )

    class Socio(Base):
        __tablename__ = 'socio'
        socio_id = Column(Integer, primary_key=True, autoincrement=True)
        nome = Column(String, nullable=False)
        nif = Column(String)
        morada = Column(String)
        eventos = relationship(
            'EventoEmpresa', back_populates='socio', cascade='all, delete-orphan'
        )

    class PDFFile(Base):
        __tablename__ = 'pdffile'
        file_id = Column(Integer, primary_key=True, autoincrement=True)
        nome = Column(String, nullable=False)
        data_upload = Column(Date, nullable=False)
        conteudo = Column(LargeBinary, nullable=False)

    class EventoEmpresa(Base):
        __tablename__ = 'evento_empresa'
        evento_id = Column(Integer, primary_key=True, autoincrement=True)
        empresa_id = Column(Integer, ForeignKey('empresa.empresa_id'), nullable=False)
        socio_id = Column(Integer, ForeignKey('socio.socio_id'), nullable=True)
        data_evento = Column(Date, nullable=False)
        tipo = Column(String, nullable=False)
        detalhes = Column(JSON)
        arquivo_pdf_id = Column(Integer, ForeignKey('pdffile.file_id'))
        empresa = relationship('Empresa', back_populates='eventos')
        socio = relationship('Socio', back_populates='eventos')
        pdf = relationship('PDFFile')

    return Empresa, Socio, PDFFile, EventoEmpresa

# ----------------------
# INICIALIZAÇÃO DB
# ----------------------

def get_engine():
    new_db = not os.path.exists(DB_FILE)
    engine = create_engine(DB_URL, connect_args={'check_same_thread': False})
    if not new_db:
        with engine.connect() as conn:
            # migrations omitted
            pass
    Base.metadata.create_all(engine)
    return engine

def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()

# ----------------------
# UTILITÁRIOS PDF
# ----------------------

def extrair_texto_pdf_bytes(pdf_bytes):
    from io import BytesIO
    text_all = ''
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text_all += page.extract_text() or ''
    return text_all

# ----------------------
# RENDERIZAÇÃO DE ABAS
# ----------------------

def render_empresas(session, Empresa):
    # ... existente ...
    pass

def render_socios(session, Socio):
    # ... existente ...
    pass

def render_upload_pdfs(session, PDFFile):
    st.header('Upload de PDFs')
    with st.form('form_upload', clear_on_submit=True):
        uploaded = st.file_uploader('Selecione PDF', type=['pdf'], accept_multiple_files=True)
        if st.form_submit_button('Upload'):
            from datetime import date
            for file in uploaded:
                pdf_bytes = file.getvalue()
                novo = PDFFile(
                    nome=file.name,
                    data_upload=date.today(),
                    conteudo=pdf_bytes
                )
                session.add(novo)
            session.commit()
            st.success('PDFs carregados com sucesso.')
    # listar PDFs
    dados = [{
        'ID': f.file_id,
        'Nome': f.nome,
        'DataUpload': f.data_upload
    } for f in session.query(PDFFile).all()]
    st.table(pd.DataFrame(dados))

def render_process_pdfs(session, PDFFile, Empresa, Socio, EventoEmpresa):
    st.header('Processamento de PDFs')
    # escolha de PDF
    pdfs = session.query(PDFFile).all()
    sel = st.selectbox('PDF armazenado', pdfs, format_func=lambda f: f.nome)
    if sel:
        texto = extrair_texto_pdf_bytes(sel.conteudo)
        st.subheader('Texto extraído')
        st.text_area('', texto, height=300)
        # Aqui implementa extração manual ou identificação de eventos
        st.subheader('Identificação de dados')
        # ... formular para reconhecer dados relevantes ...
        if st.button('Registrar eventos a partir deste PDF'):
            st.success('Eventos registrados.')


def render_visualizar(session, Empresa, Socio, EventoEmpresa):
    # ... existente ...
    pass

# ----------------------
# MAIN
# ----------------------

def main():
    Empresa, Socio, PDFFile, EventoEmpresa = define_models()
    session = get_session()
    page = st.sidebar.radio('Menu', ['Empresas','Sócios','Upload PDFs','Processar PDFs','Visualizar Dados'])
    if page == 'Empresas':
        render_empresas(session, Empresa)
    elif page == 'Sócios':
        render_socios(session, Socio)
    elif page == 'Upload PDFs':
        render_upload_pdfs(session, PDFFile)
    elif page == 'Processar PDFs':
        render_process_pdfs(session, PDFFile, Empresa, Socio, EventoEmpresa)
    else:
        render_visualizar(session, Empresa, Socio, EventoEmpresa)

if __name__ == '__main__':
    main()
