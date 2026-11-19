"""Autoavaliação estruturada v0.13; nunca equivale a teste objetivo validado."""


def inferred_grade(recall: int, accuracy: int, assistance: int, gaps: int) -> int:
    """Nota 0–4 conservadora, sem recompensar consulta ou erros relevantes.

    recall: 0 nenhum, 1 fragmentos, 2 parcial, 3 completo.
    accuracy: 0 incorreto, 1 erros importantes, 2 pequenas imprecisões, 3 preciso.
    assistance: 0 nenhuma, 1 hesitação, 2 dicas, 3 consulta.
    gaps: 0 nenhuma, 1 pequenas, 2 moderadas, 3 graves.
    """
    for v in (recall, accuracy, assistance, gaps):
        if not isinstance(v, int) or isinstance(v, bool) or v not in range(4):
            raise ValueError('Respostas do questionário devem estar entre zero e três.')
    if recall == 0:
        return 0
    if recall == 1 or accuracy == 0 or gaps == 3:
        return 1
    if recall == 2 or accuracy <= 1 or assistance >= 2 or gaps >= 2:
        return 2
    if accuracy == 3 and assistance == 0 and gaps == 0:
        return 4
    return 3
