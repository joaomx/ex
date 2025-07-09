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
    """
    Inicializa o engine SQLite, aplica migrações leves e cria tabelas.
    """
    new_db = not os.path.exists(DB_FILE)
    engine = create_engine(DB_URL, connect_args={'check_same_thread': False})
    if not new_db:
        with engine.connect() as conn:
            cols_socio = [r[1] for r in conn.execute(text("PRAGMA table_info(socio)"))]
            if 'nif' not in cols_socio:
                conn.execute(text("ALTER TABLE socio ADD COLUMN nif TEXT"))
            cols_evt = [r[1] for r in conn.execute(text("PRAGMA table_info(evento_empresa)"))]
            if 'arquivo_pdf_id' not in cols_evt:
                conn.execute(text("ALTER TABLE evento_empresa ADD COLUMN arquivo_pdf_id INTEGER"))
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
                novo = PDFFile(nome=file.name, data_upload=date.today(), conteudo=pdf_bytes)
                session.add(novo)
            session.commit()
            st.success('PDFs carregados com sucesso.')
    dados = [{'ID': f.file_id, 'Nome': f.nome, 'DataUpload': f.data_upload}
             for f in session.query(PDFFile).all()]
    st.table(pd.DataFrame(dados))


def render_process_pdfs(session, PDFFile, Empresa, Socio, EventoEmpresa):
    st.header('Processamento de PDFs')
    pdfs = session.query(PDFFile).all()
    sel = st.selectbox('PDF armazenado', pdfs, format_func=lambda f: f.nome)
    if not sel:
        return

    # Transcrição completa
    texto = extrair_texto_pdf_bytes(sel.conteudo)
    st.subheader('Transcrição Completa do PDF')
    st.text_area('Transcrição Completa', texto, height=600)

    # Eventos já registados
    registros = session.query(EventoEmpresa).filter_by(arquivo_pdf_id=sel.file_id).all()
    st.subheader('Eventos registados para este PDF')
    if registros:
        df = pd.DataFrame([{
            'ID': ev.evento_id,
            'Empresa': ev.empresa.nome if ev.empresa else None,
            'Sócio': ev.socio.nome if ev.socio else None,
            'Data': ev.data_evento,
            'Tipo': ev.tipo,
            'Detalhes': ev.detalhes
        } for ev in registros])
        st.table(df)
    else:
        st.info('Nenhum evento registado para este PDF.')

    # Escolha do tipo de evento
    tipo = st.selectbox('Tipo de Evento', [
        'Criação Empresa',
        'alteracao_contrato_aumento_capital',
        'alteracao_contrato',
        'designacao_membros',
        'cessacao_funcoes',
        'Inserir Accionista'
    ])

    # Formulário para Criação de Empresa (sem select de empresa)
    if tipo == 'Criação Empresa':
        st.subheader('Dados da Criação de Empresa')
        with st.form('form_criacao_empresa', clear_on_submit=True):
            data_ev = st.date_input('Data do Evento')
            nome_emp = st.text_input('Nome da Empresa')
            nif_emp = st.text_input('NIF/NIPC da Empresa')
            morada_emp = st.text_input('Morada da Empresa')
            cap_emp = st.text_input('Capital Social')
            submit = st.form_submit_button('Registrar Criação')
        if submit:
            try:
                nova_emp = Empresa(
                    nome=nome_emp,
                    forma_juridica='SA',  # ajuste conforme necessário
                    data_constituicao=data_ev
                )
                session.add(nova_emp)
                session.commit()
                detalhes_val = {'capital_social': cap_emp, 'morada': morada_emp}
                novo_ev = EventoEmpresa(
                    empresa_id=nova_emp.empresa_id,
                    socio_id=None,
                    data_evento=data_ev,
                    tipo=tipo,
                    detalhes=detalhes_val,
                    arquivo_pdf_id=sel.file_id
                )
                session.add(novo_ev)
                session.commit()
                st.success('Empresa criada e evento registado.')
            except Exception as e:
                session.rollback()
                st.error(f'Erro: {e}')

    # Formulário para Inserir Accionista (com select de empresa)
    elif tipo == 'Inserir Accionista':
        st.subheader('Dados do Acionista')
        with st.form('form_insert_accionista', clear_on_submit=True):
            data_ev = st.date_input('Data do Evento')
            emp_list = session.query(Empresa).all()
            emp = st.selectbox('Empresa', emp_list, format_func=lambda e: e.nome)
            nome_acc = st.text_input('Nome do Acionista')
            nif_acc = st.text_input('NIF/NIPC do Acionista')
            morada_acc = st.text_input('Morada do Acionista')
            quota_acc = st.text_input('Quota do Acionista')
            submit = st.form_submit_button('Registrar Acionista')
        if submit:
            try:
                novo_soc = Socio(nome=nome_acc, nif=nif_acc, morada=morada_acc)
                session.add(novo_soc); session.commit()
                detalhes_val = {
                    'nome_accionista': nome_acc,
                    'nif_accionista': nif_acc,
                    'morada_accionista': morada_acc,
                    'quota_accionista': quota_acc
                }
                novo_ev = EventoEmpresa(
                    empresa_id=emp.empresa_id,
                    socio_id=novo_soc.socio_id,
                    data_evento=data_ev,
                    tipo=tipo,
                    detalhes=detalhes_val,
                    arquivo_pdf_id=sel.file_id
                )
                session.add(novo_ev); session.commit()
                st.success('Acionista inserido e evento registado.')
            except Exception as e:
                session.rollback()
                st.error(f'Erro: {e}')

    # Formulário genérico para os outros tipos
    else:
        st.subheader('Dados do Evento')
        with st.form('form_process_event', clear_on_submit=True):
            data_ev = st.date_input('Data do Evento')
            emp_list = session.query(Empresa).all()
            emp = st.selectbox('Empresa', emp_list, format_func=lambda e: e.nome)
            socios = [None] + session.query(Socio).all()
            soc = st.selectbox('Sócio (opcional)', socios, format_func=lambda s: s.nome if s else 'Nenhum')
            detalhes_str = st.text_area('Detalhes do Evento', placeholder='JSON ou texto livre')
            submit = st.form_submit_button('Registrar Evento')
        if submit:
            try:
                import json
                detalhes_val = json.loads(detalhes_str) if detalhes_str.strip().startswith('{') else {'descricao': detalhes_str}
                novo_ev = EventoEmpresa(
                    empresa_id=emp.empresa_id,
                    socio_id=soc.socio_id if soc else None,
                    data_evento=data_ev,
                    tipo=tipo,
                    detalhes=detalhes_val,
                    arquivo_pdf_id=sel.file_id
                )
                session.add(novo_ev); session.commit()
                st.success('Evento registado com sucesso.')
            except Exception as e:
                session.rollback()
                st.error(f'Erro: {e}')


# ----------------------
def render_visualizar(session, Empresa, Socio, EventoEmpresa):
    st.header("Visualizar Registos")
    opc = st.radio("Mostrar", ["Empresas","Sócios","Eventos"])
    # Empresas
    if opc == "Empresas":
        st.subheader("Lista de Empresas")
        empresas = session.query(Empresa).all()
        df_emp = pd.DataFrame([{
            "ID": e.empresa_id,
            "Nome": e.nome,
            "Forma Jurídica": e.forma_juridica,
            "Data Constituição": e.data_constituicao
        } for e in empresas])
        st.table(df_emp)
        # Deleção de empresa
        with st.expander("Eliminar Empresa"):
            id_del = st.selectbox("Selecione ID da Empresa a eliminar", [e.empresa_id for e in empresas])
            confirm = st.checkbox("Confirmar eliminação da empresa")
            if st.button("Eliminar Empresa"):
                if confirm:
                    emp = session.get(Empresa, id_del)
                    if emp:
                        session.delete(emp)
                        session.commit()
                        st.success(f"Empresa {id_del} eliminada.")
                    else:
                        st.error("Empresa não encontrada.")
                else:
                    st.warning("Marque confirmar para proceder com a eliminação.")
    # Sócios
    elif opc == "Sócios":
        st.subheader("Lista de Sócios")
        socios = session.query(Socio).all()
        df_soc = pd.DataFrame([{
            "ID": s.socio_id,
            "Nome": s.nome,
            "NIF": s.nif,
            "Morada": s.morada
        } for s in socios])
        st.table(df_soc)
        # Deleção de sócio
        with st.expander("Eliminar Sócio"):
            id_del = st.selectbox("Selecione ID do Sócio a eliminar", [s.socio_id for s in socios])
            confirm = st.checkbox("Confirmar eliminação do sócio")
            if st.button("Eliminar Sócio"):
                if confirm:
                    soc = session.get(Socio, id_del)
                    if soc:
                        session.delete(soc)
                        session.commit()
                        st.success(f"Sócio {id_del} eliminado.")
                    else:
                        st.error("Sócio não encontrado.")
                else:
                    st.warning("Marque confirmar para proceder com a eliminação.")
    # Eventos
    else:
        st.subheader("Lista de Eventos")
        eventos = session.query(EventoEmpresa).all()
        df_evt = pd.DataFrame([{
            "ID": ev.evento_id,
            "Empresa": ev.empresa.nome if ev.empresa else None,
            "Sócio": ev.socio.nome if ev.socio else None,
            "Data Evento": ev.data_evento,
            "Tipo": ev.tipo,
            "Detalhes": ev.detalhes,
            "PDF ID": ev.arquivo_pdf_id
        } for ev in eventos])
        st.table(df_evt)
        # Deleção de evento
        with st.expander("Eliminar Evento"):
            id_del = st.selectbox("Selecione ID do Evento a eliminar", [ev.evento_id for ev in eventos])
            confirm = st.checkbox("Confirmar eliminação do evento")
            if st.button("Eliminar Evento"):
                if confirm:
                    ev = session.get(EventoEmpresa, id_del)
                    if ev:
                        session.delete(ev)
                        session.commit()
                        st.success(f"Evento {id_del} eliminado.")
                    else:
                        st.error("Evento não encontrado.")
                else:
                    st.warning("Marque confirmar para proceder com a eliminação.")

# ----------------------

def main():
    # Inicializa modelos e sessão
    Empresa, Socio, PDFFile, EventoEmpresa = define_models()
    session = get_session()
    # Menu lateral
    page = st.sidebar.radio('Menu', ['Empresas','Sócios','Upload PDFs','Processar PDFs','Visualizar Registos'])
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

# ----------------------
# ----------------------
if __name__ == '__main__':
    main()
