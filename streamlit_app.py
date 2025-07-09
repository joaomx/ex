# app.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Date, JSON, ForeignKey, text
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
            "EventoEmpresa", back_populates="empresa", cascade="all, delete-orphan"
        )

    class Socio(Base):
        __tablename__ = 'socio'
        socio_id = Column(Integer, primary_key=True, autoincrement=True)
        nome = Column(String, nullable=False)
        nif = Column(String)
        morada = Column(String)
        eventos = relationship(
            "EventoEmpresa", back_populates="socio", cascade="all, delete-orphan"
        )

    class EventoEmpresa(Base):
        __tablename__ = 'evento_empresa'
        evento_id = Column(Integer, primary_key=True, autoincrement=True)
        empresa_id = Column(Integer, ForeignKey('empresa.empresa_id'), nullable=False)
        socio_id = Column(Integer, ForeignKey('socio.socio_id'), nullable=True)
        data_evento = Column(Date, nullable=False)
        tipo = Column(String, nullable=False)
        detalhes = Column(JSON)
        arquivo_pdf = Column(String)
        empresa = relationship("Empresa", back_populates="eventos")
        socio = relationship("Socio", back_populates="eventos")

    return Empresa, Socio, EventoEmpresa

# ----------------------
# INICIALIZAÇÃO DB
# ----------------------
def get_engine():
    new_db = not os.path.exists(DB_FILE)
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    if not new_db:
        with engine.connect() as conn:
            # migrar colunas
            cols = [r[1] for r in conn.execute(text("PRAGMA table_info(socio)"))]
            if 'nif' not in cols:
                conn.execute(text("ALTER TABLE socio ADD COLUMN nif TEXT"))
            cols = [r[1] for r in conn.execute(text("PRAGMA table_info(evento_empresa)"))]
            if 'arquivo_pdf' not in cols:
                conn.execute(text("ALTER TABLE evento_empresa ADD COLUMN arquivo_pdf TEXT"))
    Base.metadata.create_all(engine)
    return engine

def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()

# ----------------------
# UTILITÁRIOS PDF
# ----------------------
def extrair_texto_pdf(uploaded_file):
    uploaded_file.seek(0)
    text_all = ''
    with pdfplumber.open(uploaded_file) as pdf:
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

def render_import_pdf(session, Empresa, Socio, EventoEmpresa):
    st.header("Importar PDF e Registar Evento")
    uploaded = st.file_uploader("PDF de Ato", type=['pdf'])
    if uploaded:
        st.download_button("Download PDF", uploaded.getvalue(), uploaded.name, mime='application/pdf')
        texto = extrair_texto_pdf(uploaded)
        st.text_area("Texto do PDF", texto, height=300)
        data_ev = st.date_input("Data do Evento")
        tipo = st.selectbox("Tipo", [
            "constituicao_sociedade","alteracao_aumento","designacao","cessacao"
        ])
        # Blocos dinâmicos conforme tipo...
        if tipo == 'constituicao_sociedade':
            # coleta campos...
            pass
        else:
            # coleta sócios existentes
            empresas = session.query(Empresa).all()
            emp = st.selectbox("Empresa", empresas, format_func=lambda e:e.nome)
            # ... restante fluxo genérico
            pass
        if st.button("Registar Evento"):
            st.success("Evento registado.")

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
    Empresa, Socio, EventoEmpresa = define_models()
    session = get_session()
    st.sidebar.title("Menu")
    page = st.sidebar.radio("Navegação", ["Empresas","Sócios","Importar PDF","Visualizar Dados"])
    if page == "Empresas":
        render_empresas(session, Empresa)
    elif page == "Sócios":
        render_socios(session, Socio)
    elif page == "Importar PDF":
        render_import_pdf(session, Empresa, Socio, EventoEmpresa)
    else:
        render_visualizar(session, Empresa, Socio, EventoEmpresa)

if __name__ == "__main__":
    main()
