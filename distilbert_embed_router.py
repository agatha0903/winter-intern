import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel

MODEL_NAME = "distilbert-base-uncased"  # 영어용

INTENT_TEMPLATES = {
    "STOP": [
        "stop",
        "please stop",
        "pause now",
        "hold on",
        "don't move",
    ],
    "START": [
        "start",
        "begin",
        "continue",
        "you can start now",
        "go ahead",
    ],
}

def mean_pool(last_hidden_state, attention_mask):
    mask = attention_mask.unsqueeze(-1).float()
    summed = (last_hidden_state * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    return summed / counts

@torch.inference_mode()
def encode(texts, tokenizer, model, device):
    batch = tokenizer(texts, padding=True, truncation=True, return_tensors="pt").to(device)
    out = model(**batch)
    emb = mean_pool(out.last_hidden_state, batch["attention_mask"])
    emb = F.normalize(emb, p=2, dim=1)
    return emb

def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("device:", device)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME).to(device)
    model.eval()

    # 템플릿 임베딩 미리 계산
    intent_names = []
    intent_embs = []
    for intent, texts in INTENT_TEMPLATES.items():
        e = encode(texts, tokenizer, model, device)          # (k, d)
        e = e.mean(dim=0, keepdim=True)                      # (1, d) 평균 템플릿
        intent_names.append(intent)
        intent_embs.append(e)
    intent_embs = torch.cat(intent_embs, dim=0)              # (num_intents, d)

    print("\nQuit: q\n")
    while True:
        utt = input("User says > ").strip()
        if utt.lower() == "q":
            break
        if not utt:
            continue

        q = encode([utt], tokenizer, model, device)          # (1, d)
        sims = (q @ intent_embs.T)[0]                        # cosine similarity
        best_idx = int(torch.argmax(sims).item())
        print("scores:", {intent_names[i]: float(sims[i]) for i in range(len(intent_names))})
        print("CHOSEN:", intent_names[best_idx], "\n")

if __name__ == "__main__":
    main()
