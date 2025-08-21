from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import json

# Google Calendar imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_muito_forte_aqui'

# Configuração do banco de dados SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pacientes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuração Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_SECRETS_FILE = "credentials.json"  # Baixe do Google Cloud Console

db = SQLAlchemy(app)

# Modelo do Paciente
class Paciente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    endereco = db.Column(db.Text)
    observacoes_medicas = db.Column(db.Text)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamento com atendimentos
    atendimentos = db.relationship('Atendimento', backref='paciente', lazy=True)

# Modelo do Atendimento
class Atendimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    data_atendimento = db.Column(db.DateTime, nullable=False)
    profissional = db.Column(db.String(100), nullable=False)
    tratamento = db.Column(db.String(100), nullable=False)
    observacoes = db.Column(db.Text)
    evolucao = db.Column(db.Text)
    evento_calendar_id = db.Column(db.String(255))

# Modelo para armazenar credenciais do Google
class GoogleCredentials(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), unique=True, nullable=False)
    credentials = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Criar as tabelas
@app.before_first_request
def create_tables():
    db.create_all()

def get_google_calendar_service():
    """Retorna o serviço do Google Calendar se autenticado"""
    cred_record = GoogleCredentials.query.first()
    if not cred_record:
        return None
    
    try:
        creds_data = json.loads(cred_record.credentials)
        creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        
        # Refresh token se necessário
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Atualizar credenciais no banco
            cred_record.credentials = creds.to_json()
            db.session.commit()
        
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"Erro ao obter serviço do Google Calendar: {e}")
        return None

def create_calendar_event(paciente, atendimento):
    """Cria evento no Google Calendar"""
    service = get_google_calendar_service()
    if not service:
        return None
    
    try:
        # Preparar dados do evento
        start_time = atendimento.data_atendimento
        end_time = start_time + timedelta(hours=1)  # Duração padrão de 1 hora
        
        event = {
            'summary': f'Atendimento - {paciente.nome}',
            'description': f'Paciente: {paciente.nome}\nTelefone: {paciente.telefone}\nTratamento: {atendimento.tratamento}\n\nObservações: {atendimento.observacoes or "Nenhuma"}',
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'America/Sao_Paulo',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/Sao_Paulo',
            },
            'attendees': [
                {'email': paciente.email} if paciente.email else None
            ],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 dia antes
                    {'method': 'popup', 'minutes': 30},       # 30 min antes
                ],
            },
        }
        
        # Remover attendees None
        if not paciente.email:
            event['attendees'] = []
        
        # Criar evento
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return created_event.get('id')
        
    except HttpError as error:
        print(f'Erro ao criar evento no Google Calendar: {error}')
        return None

@app.route('/')
def index():
    pacientes = Paciente.query.all()
    return render_template('index.html', pacientes=pacientes)

@app.route('/novo_paciente', methods=['GET', 'POST'])
def novo_paciente():
    if request.method == 'POST':
        nome = request.form['nome']
        telefone = request.form['telefone']
        email = request.form.get('email', '')
        endereco = request.form.get('endereco', '')
        observacoes_medicas = request.form.get('observacoes_medicas', '')
        
        # Criar novo paciente
        paciente = Paciente(
            nome=nome,
            telefone=telefone,
            email=email if email else None,
            endereco=endereco if endereco else None,
            observacoes_medicas=observacoes_medicas if observacoes_medicas else None
        )
        
        try:
            db.session.add(paciente)
            db.session.commit()
            flash(f'Paciente {nome} cadastrado com sucesso!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao cadastrar paciente. Tente novamente.', 'error')
            
    return render_template('novo_paciente.html')

@app.route('/paciente/<int:id>')
def visualizar_paciente(id):
    paciente = Paciente.query.get_or_404(id)
    atendimentos = Atendimento.query.filter_by(paciente_id=id).order_by(Atendimento.data_atendimento.desc()).all()
    return render_template('paciente.html', paciente=paciente, atendimentos=atendimentos)

@app.route('/buscar', methods=['GET', 'POST'])
def buscar_paciente():
    pacientes = []
    if request.method == 'GET' and request.args.get('q'):
        query = request.args.get('q')
        pacientes = Paciente.query.filter(
            db.or_(
                Paciente.nome.contains(query),
                Paciente.telefone.contains(query),
                Paciente.email.contains(query) if query else False
            )
        ).all()
    
    return render_template('buscar_paciente.html', pacientes=pacientes)

@app.route('/novo_atendimento/<int:paciente_id>', methods=['GET', 'POST'])
def novo_atendimento(paciente_id):
    paciente = Paciente.query.get_or_404(paciente_id)
    
    if request.method == 'POST':
        data_atendimento_str = request.form['data_atendimento']
        data_atendimento = datetime.fromisoformat(data_atendimento_str)
        profissional = request.form['profissional']
        tratamento = request.form['tratamento']
        
        # Se tratamento for "Outros", pega o valor customizado
        if tratamento == 'Outros':
            tratamento = request.form.get('tratamento_customizado', 'Outros')
        
        observacoes = request.form.get('observacoes', '')
        evolucao = request.form.get('evolucao', '')
        agendar_google = 'agendar_google' in request.form
        
        # Criar novo atendimento
        atendimento = Atendimento(
            paciente_id=paciente_id,
            data_atendimento=data_atendimento,
            profissional=profissional,
            tratamento=tratamento,
            observacoes=observacoes if observacoes else None,
            evolucao=evolucao if evolucao else None
        )
        
        try:
            db.session.add(atendimento)
            db.session.flush()  # Para obter o ID do atendimento
            
            # Agendar no Google Calendar se solicitado
            if agendar_google:
                event_id = create_calendar_event(paciente, atendimento)
                if event_id:
                    atendimento.evento_calendar_id = event_id
                    flash('Atendimento agendado no Google Calendar!', 'success')
                else:
                    flash('Atendimento registrado, mas não foi possível agendar no Google Calendar. Verifique a conexão.', 'warning')
            
            db.session.commit()
            flash(f'Atendimento registrado com sucesso para {paciente.nome}!', 'success')
            return redirect(url_for('visualizar_paciente', id=paciente_id))
            
        except Exception as e:
            db.session.rollback()
            flash('Erro ao registrar atendimento. Tente novamente.', 'error')
            print(f"Erro: {e}")
    
    return render_template('novo_atendimento.html', paciente=paciente)

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar_paciente(id):
    paciente = Paciente.query.get_or_404(id)
    
    if request.method == 'POST':
        paciente.nome = request.form['nome']
        paciente.telefone = request.form['telefone']
        paciente.email = request.form.get('email', '') or None
        paciente.endereco = request.form.get('endereco', '') or None
        paciente.observacoes_medicas = request.form.get('observacoes_medicas', '') or None
        
        try:
            db.session.commit()
            flash(f'Dados de {paciente.nome} atualizados com sucesso!', 'success')
            return redirect(url_for('visualizar_paciente', id=id))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao atualizar dados. Tente novamente.', 'error')
    
    return render_template('editar_paciente.html', paciente=paciente)

@app.route('/api/pacientes')
def api_pacientes():
    query = request.args.get('q', '')
    if len(query) >= 2:
        pacientes = Paciente.query.filter(
            db.or_(
                Paciente.nome.contains(query),
                Paciente.telefone.contains(query),
                Paciente.email.contains(query) if query else False
            )
        ).limit(10).all()
        
        return jsonify([{
            'id': p.id,
            'nome': p.nome,
            'telefone': p.telefone,
            'email': p.email or ''
        } for p in pacientes])
    
    return jsonify([])

# Google Calendar Routes
@app.route('/auth_google')
def auth_google():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        flash('Arquivo de credenciais do Google não encontrado. Configure o Google Calendar API primeiro.', 'error')
        return redirect(url_for('calendar_status'))
    
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    
    flow.fetch_token(authorization_response=request.url)
    
    credentials = flow.credentials
    
    # Salvar credenciais no banco
    cred_record = GoogleCredentials.query.first()
    if cred_record:
        cred_record.credentials = credentials.to_json()
    else:
        cred_record = GoogleCredentials(
            user_id='default_user',
            credentials=credentials.to_json()
        )
        db.session.add(cred_record)
    
    db.session.commit()
    
    flash('Google Calendar conectado com sucesso!', 'success')
    return redirect(url_for('calendar_status'))

@app.route('/disconnect_calendar')
def disconnect_calendar():
    cred_record = GoogleCredentials.query.first()
    if cred_record:
        db.session.delete(cred_record)
        db.session.commit()
        flash('Google Calendar desconectado!', 'success')
    
    return redirect(url_for('calendar_status'))

@app.route('/calendar_status')
def calendar_status():
    cred_record = GoogleCredentials.query.first()
    calendar_connected = cred_record is not None
    
    user_email = ''
    total_eventos = 0
    eventos_hoje = 0
    
    if calendar_connected:
        service = get_google_calendar_service()
        if service:
            try:
                # Obter informações do usuário
                calendar_info = service.calendars().get(calendarId='primary').execute()
                user_email = calendar_info.get('summary', 'Usuário conectado')
                
                # Contar eventos sincronizados (atendimentos com evento_calendar_id)
                total_eventos = Atendimento.query.filter(Atendimento.evento_calendar_id.isnot(None)).count()
                
                # Contar eventos hoje
                hoje = datetime.now().date()
                eventos_hoje = Atendimento.query.filter(
                    Atendimento.evento_calendar_id.isnot(None),
                    db.func.date(Atendimento.data_atendimento) == hoje
                ).count()
                
            except Exception as e:
                print(f"Erro ao obter informações do calendar: {e}")
    
    return render_template('calendar_status.html', 
                         calendar_connected=calendar_connected, 
                         user_email=user_email, 
                         total_eventos=total_eventos, 
                         eventos_hoje=eventos_hoje)

@app.route('/sync_calendar')
def sync_calendar():
    """Sincroniza atendimentos pendentes com o Google Calendar"""
    service = get_google_calendar_service()
    if not service:
        flash('Google Calendar não conectado!', 'error')
        return redirect(url_for('calendar_status'))
    
    # Buscar atendimentos sem evento no calendar
    atendimentos_pendentes = Atendimento.query.filter(
        Atendimento.evento_calendar_id.is_(None),
        Atendimento.data_atendimento >= datetime.now()
    ).all()
    
    sincronizados = 0
    for atendimento in atendimentos_pendentes:
        paciente = atendimento.paciente
        event_id = create_calendar_event(paciente, atendimento)
        if event_id:
            atendimento.evento_calendar_id = event_id
            sincronizados += 1
    
    if sincronizados > 0:
        db.session.commit()
        flash(f'{sincronizados} atendimentos sincronizados com o Google Calendar!', 'success')
    else:
        flash('Nenhum atendimento pendente para sincronizar.', 'info')
    
    return redirect(url_for('calendar_status'))

if __name__ == '__main__':
    app.run(debug=True)
