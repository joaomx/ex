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
    st.header("Adicionar Nova Empresa")
    with st.form('form_empresa', clear_on_submit=True):
        nome = st.text_input("Nome da Empresa")
        forma = st.selectbox("Forma Jurídica", ["Lda","SA","Unipessoal","Cooperativa"])
        data_const = st.date_input("Data de Constituição")
        if st.form_submit_button("Guardar Empresa"):
            try:
                nova = Empresa(nome=nome, forma_juridica=forma, data_constituicao=data_const)
                session.add(nova); session.commit()
                st.success("Empresa adicionada.")
            except Exception as e:
                session.rollback(); st.error(f"Erro: {e}")
    # tabela
    dados = [{"ID":e.empresa_id,"Nome":e.nome,"Forma":e.forma_juridica,"Data":e.data_constituicao}
             for e in session.query(Empresa).all()]
    st.table(pd.DataFrame(dados))

def render_socios(session, Socio):
    st.header("Adicionar/Ver Sócios")
    with st.form('form_socio', clear_on_submit=True):
        nome = st.text_input("Nome do Sócio")
        nif = st.text_input("NIF/NIPC")
        morada = st.text_input("Morada")
        if st.form_submit_button("Guardar Sócio"):
            try:
                novo = Socio(nome=nome, nif=nif, morada=morada)
                session.add(novo); session.commit()
                st.success("Sócio adicionado.")
            except Exception as e:
                session.rollback(); st.error(f"Erro: {e}")
    dados = [{"ID":s.socio_id,"Nome":s.nome,"NIF":s.nif,"Morada":s.morada}
             for s in session.query(Socio).all()]
    st.table(pd.DataFrame(dados))

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
    pdfs = session.query(PDFFile).all()
    sel = st.selectbox('PDF armazenado', pdfs, format_func=lambda f: f.nome)
    if sel:
        texto = extrair_texto_pdf_bytes(sel.conteudo)
        col1, col2 = st.columns(2)
        # Coluna da esquerda: tabela de eventos existentes
        with col1:
            st.subheader('Eventos registados')
            registros = session.query(EventoEmpresa).filter_by(arquivo_pdf_id=sel.file_id).all()
            if registros:
                dados = []
                for ev in registros:
                    dados.append({
                        'ID': ev.evento_id,
                        'Empresa': ev.empresa.nome if ev.empresa else None,
                        'Sócio': ev.socio.nome if ev.socio else None,
                        'Data': ev.data_evento,
                        'Tipo': ev.tipo
                    })
                st.table(pd.DataFrame(dados))
            else:
                st.info('Nenhum evento registado para este PDF.')
        # Coluna da direita: formulário de registo de novo evento
        with col2:
            st.subheader('Registar Novo Evento')
            with st.form('form_process_pdf'):
                data_ev = st.date_input('Data do Evento')
                tipo = st.selectbox('Tipo de Evento', [
                    'constituicao_sociedade',
                    'alteracao_contrato_aumento_capital',
                    'alteracao_contrato',
                    'designacao_membros',
                    'cessacao_funcoes'
                ])
                empresas = session.query(Empresa).all()
                emp = st.selectbox('Empresa', empresas, format_func=lambda e: e.nome)
                socios = [None] + session.query(Socio).all()
                soc = st.selectbox('Sócio (opcional)', socios, format_func=lambda s: s.nome if s else 'Nenhum')
                detalhes_str = st.text_area('Detalhes do Evento', placeholder='JSON ou texto livre')
                submitted = st.form_submit_button('Registrar Evento')
            if submitted:
                try:
                    import json
                    try:
                        detalhes_val = json.loads(detalhes_str)
                    except Exception:
                        detalhes_val = {'descricao': detalhes_str}
                    novo_ev = EventoEmpresa(
                        empresa_id=emp.empresa_id,
                        socio_id=soc.socio_id if soc else None,
                        data_evento=data_ev,
                        tipo=tipo,
                        detalhes=detalhes_val,
                        arquivo_pdf_id=sel.file_id
                    )
                    session.add(novo_ev)
                    session.commit()
                    st.success('Evento registado com sucesso.')
                except Exception as e:
                    session.rollback()
                    st.error(f'Erro ao registar evento: {e}')
# ----------------------
# Aba Visualizar
def render_visualizar(session, Empresa, Socio, EventoEmpresa):
    st.header("Visualizar Registos")
    opc = st.radio("Mostrar", ["Empresas","Sócios","Eventos"])
    if opc == "Empresas":
        df = pd.DataFrame([{"ID":e.empresa_id,"Nome":e.nome} for e in session.query(Empresa).all()])
        st.table(df)
    elif opc == "Sócios":
        df = pd.DataFrame([{"ID":s.socio_id,"Nome":s.nome} for s in session.query(Socio).all()])
        st.table(df)
    else:
        df = pd.DataFrame([{"ID":ev.evento_id,"Tipo":ev.tipo} for ev in session.query(EventoEmpresa).all()])
        st.table(df)


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
