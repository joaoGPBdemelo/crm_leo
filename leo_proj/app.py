from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'

# Configuração do banco de dados SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pacientes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

# Criar as tabelas
@app.before_first_request
def create_tables():
    db.create_all()

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
            db.session.commit()
            flash(f'Atendimento registrado com sucesso para {paciente.nome}!', 'success')
            return redirect(url_for('visualizar_paciente', id=paciente_id))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao registrar atendimento. Tente novamente.', 'error')
    
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

@app.route('/auth_google')
def auth_google():
    return "Google Auth não implementado ainda"

@app.route('/calendar_status')
def calendar_status():
    # Dados fictícios por enquanto
    return render_template('calendar_status.html', 
                         calendar_connected=False, 
                         user_email='', 
                         total_eventos=0, 
                         eventos_hoje=0)

if __name__ == '__main__':
    app.run(debug=True)
