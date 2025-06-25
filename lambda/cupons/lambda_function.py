import json
import boto3
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List

# Configurar logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Inicializar cliente DynamoDB
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('DYNAMODB_TABLE', 'cupons')
table = dynamodb.Table(table_name)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handler principal da Lambda para API de cupons
    """
    try:
        logger.info(f"Evento recebido: {json.dumps(event)}")
        
        # Extrair informações da requisição
        http_method = event.get('httpMethod')
        path = event.get('path')
        path_parameters = event.get('pathParameters') or {}
        query_parameters = event.get('queryStringParameters') or {}
        
        # Roteamento baseado no método e path
        if http_method == 'GET':
            if path == '/cupons':
                return listar_cupons_disponiveis(query_parameters)
            elif path.startswith('/cupons/') and 'id' in path_parameters:
                cupom_id = path_parameters['id']
                # Verificar se é para usar o cupom ou apenas visualizar
                usar_cupom = query_parameters.get('usar', 'true').lower() == 'true'
                if usar_cupom:
                    return usar_cupom_por_id(cupom_id)
                else:
                    return visualizar_cupom_por_id(cupom_id)
        
        # Rota não encontrada
        return criar_resposta(404, {'error': 'Rota não encontrada'})
        
    except Exception as e:
        logger.error(f"Erro no processamento: {str(e)}")
        return criar_resposta(500, {'error': 'Erro interno do servidor'})

def listar_cupons_disponiveis(query_parameters: Dict[str, str]) -> Dict[str, Any]:
    """
    Lista todos os cupons disponíveis (status = 'disponivel')
    """
    try:
        logger.info("Listando cupons disponíveis")
        
        # Parâmetros de paginação
        limit = int(query_parameters.get('limit', 20))
        
        # Query no GSI por status
        response = table.query(
            IndexName='status-index',
            KeyConditionExpression='#status = :status',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'disponivel'
            },
            Limit=limit
        )
        
        # Formatar cupons para retorno simplificado
        cupons = []
        for item in response['Items']:
            cupom_formatado = {
                'codigo': item['cupom_id'],
                'desconto': float(item['valor']) / 100.0 if item['tipo'] == 'percentual' else 0.0
            }
            cupons.append(cupom_formatado)
        
        resultado = {
            'cupons': cupons,
            'total': len(cupons),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Encontrados {len(cupons)} cupons disponíveis")
        return criar_resposta(200, resultado)
        
    except Exception as e:
        logger.error(f"Erro ao listar cupons: {str(e)}")
        return criar_resposta(500, {'error': 'Erro ao buscar cupons'})

def usar_cupom_por_id(cupom_id: str) -> Dict[str, Any]:
    """
    Busca um cupom específico por ID e registra seu uso
    """
    try:
        logger.info(f"Buscando e usando cupom: {cupom_id}")
        
        # Primeiro, verificar se o cupom existe e está disponível
        response = table.get_item(
            Key={'cupom_id': cupom_id}
        )
        
        if 'Item' not in response:
            logger.warning(f"Cupom não encontrado: {cupom_id}")
            return criar_resposta(404, {'error': 'Cupom não encontrado'})
        
        item = response['Item']
        
        # Verificar se o cupom está disponível
        if item['status'] != 'disponivel':
            logger.warning(f"Cupom não disponível: {cupom_id} - Status: {item['status']}")
            return criar_resposta(400, {'error': 'Cupom não está disponível'})
        
        # Verificar se ainda tem usos disponíveis
        uso_atual = int(item.get('uso_atual', 0))
        uso_maximo = int(item.get('uso_maximo', 0))
        
        if uso_atual >= uso_maximo:
            logger.warning(f"Cupom esgotado: {cupom_id} - Usos: {uso_atual}/{uso_maximo}")
            return criar_resposta(400, {'error': 'Cupom esgotado'})
        
        # Incrementar o uso do cupom usando atomic counter
        novo_uso = uso_atual + 1
        novo_status = 'esgotado' if novo_uso >= uso_maximo else 'disponivel'
        
        # Atualizar o cupom no DynamoDB
        update_response = table.update_item(
            Key={'cupom_id': cupom_id},
            UpdateExpression='SET uso_atual = :novo_uso, #status = :novo_status',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':novo_uso': novo_uso,
                ':novo_status': novo_status
            },
            ReturnValues='UPDATED_NEW'
        )
        
        # Formatar cupom para retorno simplificado
        cupom_formatado = {
            'codigo': item['cupom_id'],
            'desconto': float(item['valor']) / 100.0 if item['tipo'] == 'percentual' else 0.0,
            'usos_restantes': uso_maximo - novo_uso,
            'status': novo_status
        }
        
        logger.info(f"Cupom usado com sucesso: {cupom_id} - Uso: {novo_uso}/{uso_maximo}")
        return criar_resposta(200, cupom_formatado)
        
    except Exception as e:
        logger.error(f"Erro ao buscar cupom {cupom_id}: {str(e)}")
        return criar_resposta(500, {'error': 'Erro ao buscar cupom'})

def visualizar_cupom_por_id(cupom_id: str) -> Dict[str, Any]:
    """
    Visualiza um cupom específico por ID sem registrar uso
    """
    try:
        logger.info(f"Visualizando cupom: {cupom_id}")
        
        # Buscar item na tabela
        response = table.get_item(
            Key={'cupom_id': cupom_id}
        )
        
        if 'Item' not in response:
            logger.warning(f"Cupom não encontrado: {cupom_id}")
            return criar_resposta(404, {'error': 'Cupom não encontrado'})
        
        # Formatar cupom para retorno simplificado
        item = response['Item']
        uso_atual = int(item.get('uso_atual', 0))
        uso_maximo = int(item.get('uso_maximo', 0))
        
        cupom_formatado = {
            'codigo': item['cupom_id'],
            'desconto': float(item['valor']) / 100.0 if item['tipo'] == 'percentual' else 0.0,
            'usos_restantes': uso_maximo - uso_atual,
            'status': item['status']
        }
        
        logger.info(f"Cupom visualizado: {cupom_id}")
        return criar_resposta(200, cupom_formatado)
        
    except Exception as e:
        logger.error(f"Erro ao visualizar cupom {cupom_id}: {str(e)}")
        return criar_resposta(500, {'error': 'Erro ao visualizar cupom'})

def converter_decimal_to_float(obj):
    """
    Converte objetos Decimal do DynamoDB para float para serialização JSON
    """
    if isinstance(obj, list):
        return [converter_decimal_to_float(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: converter_decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj

def criar_resposta(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cria resposta HTTP padronizada
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(body, ensure_ascii=False)
    }

def popular_dados_teste():
    """
    Função para popular dados de teste (executar apenas uma vez)
    """
    cupons_teste = [
        {
            'cupom_id': 'DESCONTO10',
            'nome': 'Desconto 10%',
            'descricao': 'Desconto de 10% em todas as entregas',
            'tipo': 'percentual',
            'valor': Decimal('10.0'),
            'valor_minimo': Decimal('50.0'),
            'status': 'disponivel',
            'data_criacao': datetime.now(timezone.utc).isoformat(),
            'data_expiracao': '2024-12-31T23:59:59Z',
            'uso_maximo': 100,
            'uso_atual': 0
        },
        {
            'cupom_id': 'FRETE_GRATIS',
            'nome': 'Frete Grátis',
            'descricao': 'Frete grátis para pedidos acima de R$ 100',
            'tipo': 'frete_gratis',
            'valor': Decimal('0.0'),
            'valor_minimo': Decimal('100.0'),
            'status': 'disponivel',
            'data_criacao': datetime.now(timezone.utc).isoformat(),
            'data_expiracao': '2024-12-31T23:59:59Z',
            'uso_maximo': 200,
            'uso_atual': 5
        },
        {
            'cupom_id': 'DESCONTO25',
            'nome': 'Super Desconto 25%',
            'descricao': 'Desconto especial de 25% para novos clientes',
            'tipo': 'percentual',
            'valor': Decimal('25.0'),
            'valor_minimo': Decimal('200.0'),
            'status': 'disponivel',
            'data_criacao': datetime.now(timezone.utc).isoformat(),
            'data_expiracao': '2024-12-31T23:59:59Z',
            'uso_maximo': 50,
            'uso_atual': 12
        },
        {
            'cupom_id': 'ESGOTADO',
            'nome': 'Cupom Esgotado',
            'descricao': 'Este cupom já foi totalmente utilizado',
            'tipo': 'percentual',
            'valor': Decimal('15.0'),
            'valor_minimo': Decimal('75.0'),
            'status': 'esgotado',
            'data_criacao': datetime.now(timezone.utc).isoformat(),
            'data_expiracao': '2024-12-31T23:59:59Z',
            'uso_maximo': 10,
            'uso_atual': 10
        }
    ]
    
    # Inserir cupons na tabela
    for cupom in cupons_teste:
        try:
            table.put_item(Item=cupom)
            logger.info(f"Cupom inserido: {cupom['cupom_id']}")
        except Exception as e:
            logger.error(f"Erro ao inserir cupom {cupom['cupom_id']}: {str(e)}")