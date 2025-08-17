# Handball Stats App — Setup Rápido

Este pacote contém scripts para preparar e iniciar rapidamente a tua aplicação **Streamlit** (`teste.py`) com ficheiro Excel `Plantel.xlsx`.

## Conteúdo
- `setup_and_start.command` (macOS): duplo clique → abre o Terminal, faz setup e arranca a app.
- `setup_and_start.bat` (Windows): duplo clique → faz setup e arranca a app.
- `setup.sh` (macOS/Linux): cria/ativa venv, instala dependências.
- `requirements.txt`: dependências do projeto (Streamlit, Pandas, Openpyxl, Watchdog, ...).

> Coloca estes ficheiros **na mesma pasta** onde tens o `teste.py` e o `Plantel.xlsx`.

---

## Como usar (macOS)
1. Mover ficheiros para a pasta do projeto (onde está o `teste.py`).
2. Na 1ª vez, dar permissões:
   ```bash
   chmod +x setup.sh setup_and_start.command
   ```
3. Dar **duplo clique** em `setup_and_start.command`.

Se o macOS bloquear por segurança, vai a **System Settings → Privacy & Security → Open Anyway**.

## Como usar (Windows)
1. Mover ficheiros para a pasta do projeto (onde está o `teste.py`).
2. **Duplo clique** em `setup_and_start.bat`.

---

## Estrutura do Excel `Plantel.xlsx`

A aplicação espera as seguintes abas/sheets:

### Aba **Info**
- **Coluna A:** Equipa A
- **Coluna B:** Equipa B
- **Coluna C:** Data (YYYY-MM-DD ou texto livre)
- **Coluna D:** Local

### Aba **Atletas**
- **Coluna A:** Numero (inteiro; GR e jogadores de campo usam o seu número)
- **Coluna B:** Nome
- **Coluna C:** Posição — usar **GR** para guarda-redes; outras posições para jogadores de campo

> Máximo: 16 atletas no total (7 em campo + 9 banco).

### Aba **Oficiais**
- **Coluna A:** Nome
- **Coluna B:** Posição do Oficial — **A, B, C, D ou E** (máx. 5 oficiais)

---

## Notas do funcionamento da app

- O cronómetro só **começa** quando tiverem **7 jogadores em campo**.
- Pode-se **dar Play/Pause**; quando está em pausa aparece **PAUSADO**.
- Os jogadores aparecem em **listas** separadas:
  - **Guarda-redes (GR)** primeiro;
  - **Jogadores de Campo** depois;
  - **Oficiais** no fim (só têm **botão de sanção**).
- As sanções seguem as regras acordadas (amarelos limitados, 2', vermelhos, desqualificação, etc.).
- O botão **Remate** abre um **popup** com categorias (Golo, Defendido, Falhado) e tipos (9m, 6m, etc.).
- Se o tipo exigir **Zona**, surge um popup de **Zonas 1..8** (com compatibilidades por tipo).
- O botão **Falha Técnica** regista ações técnicas negativas do atleta.
- Existe um **toggle de Passivo** abaixo do cronómetro (desliga ao registar uma ação).
- Topo da página mostra **Resultado** (Golos Marcados x Golos Sofridos) + totais por parte.

---

## Dicas
- Se não houver `Plantel.xlsx` na pasta, a app vai pedir upload pelo **uploader**.
- Para atualizar dependências: `pip install -r requirements.txt`.
- Para atualizar o `pip`: `python -m pip install --upgrade pip`.

Bom jogo! 🏐
