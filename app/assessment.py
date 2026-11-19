"""Avaliação estruturada v0.14: evidências declaradas, não prova objetiva.

A coleta acontece em duas etapas: recuperar antes de consultar, e só então
conferir precisão/lacunas. Aplicação em outro contexto é opcional; ausência de
observação não equivale a fracasso.
"""


def inferred_grade(recall: int, accuracy: int, assistance: int, gaps: int,
                   application: int | None = None) -> int:
    """Nota 0–4, conservadora e limitada por erros, ajuda e aplicação falha.

    recall: 0 nenhum, 1 fragmentos, 2 parcial, 3 completo.
    accuracy: 0 incorreto, 1 erros importantes, 2 pequenas imprecisões, 3 preciso.
    assistance: 0 nenhuma, 1 hesitação, 2 dicas, 3 consulta.
    gaps: 0 nenhuma, 1 pequenas, 2 moderadas, 3 graves.
    application: None não testada, 0 falhou, 1 parcial, 2 independente.
    """
    for value in (recall, accuracy, assistance, gaps):
        if type(value) is not int or value not in range(4):
            raise ValueError('Respostas do questionário devem estar entre zero e três.')
    if application is not None and (type(application) is not int or application not in (0, 1, 2)):
        raise ValueError('Aplicação deve ser não testada, não conseguida, parcial ou independente.')

    # Uma impressão de ter lembrado não compensa incorreções conceituais nem
    # recuperação obtida pela consulta. As restrições não podem ser vencidas
    # pela combinação de outras respostas positivas.
    if recall == 0:
        result = 0
    elif recall == 1 or accuracy == 0 or gaps == 3:
        result = 1
    elif recall == 2 or accuracy == 1 or assistance >= 2 or gaps >= 2:
        result = 2
    elif recall == 3 and accuracy == 3 and assistance == 0 and gaps == 0:
        result = 4
    else:
        result = 3

    if accuracy == 0:
        result = min(result, 1)
    if accuracy == 1 or assistance == 3 or gaps >= 3:
        result = min(result, 1)
    if assistance == 2 or gaps == 2:
        result = min(result, 2)
    if application == 0:
        result = min(result, 2)
    elif application == 1:
        result = min(result, 3)
    return result


def qualifies_as_spaced_success(review) -> bool:
    """Evidência autoavaliada suficientemente forte, sem confundir com teste.

    Registros anteriores sem questionário continuam interpretáveis por sua
    nota manual, mas essa condição será identificada separadamente na auditoria.
    """
    if review.grade < 3 or bool(getattr(review, 'critical_gap', False)):
        return False
    recall = getattr(review, 'recall_level', None)
    if recall is None:
        return True  # compatibilidade; origem legada identificada na auditoria
    return (recall >= 2 and getattr(review, 'accuracy_level', None) is not None
            and review.accuracy_level >= 2
            and getattr(review, 'assistance_level', None) is not None
            and review.assistance_level <= 1
            and getattr(review, 'application_level', None) != 0)
