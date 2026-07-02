# backend/finetune/train.py
import sys
print("[ARIS Finetuner] Initializing script and loading ML libraries (takes 6-8 seconds)...")
sys.stdout.flush()

"""
QLoRA Fine-Tuning pipeline for ARIS models on Windows.
Trains models, merges weights on CPU to save VRAM, converts to GGUF, and registers in Ollama.
"""

# Load datasets first to avoid pyarrow/torch DLL load conflict and segmentation faults on Windows
from datasets import load_dataset
import os
import sys
import subprocess
import argparse
import json
import torch
import shutil
from dotenv import load_dotenv
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, PeftModel
from trl import SFTTrainer, SFTConfig

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(BASE_DIR)
PROJECT_DIR = os.path.dirname(BACKEND_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")

# Load environment variables
load_dotenv(os.path.join(PROJECT_DIR, ".env"))
ADAPTERS_DIR = os.path.join(BASE_DIR, "adapters")
MERGED_DIR = os.path.join(BASE_DIR, "merged")
GGUF_DIR = os.path.join(BASE_DIR, "gguf")
CONVERTER_PATH = os.path.join(BASE_DIR, "llama.cpp", "convert_hf_to_gguf.py")

# Create directories
for d in [ADAPTERS_DIR, MERGED_DIR, GGUF_DIR]:
    os.makedirs(d, exist_ok=True)

# Configuration mapping
MODEL_CONFIGS = {
    "qwen3": {
        "hf_repo": "unsloth/Qwen2.5-7B-Instruct",
        "dataset_file": "qwen3_train.jsonl",
        "ollama_name": "aris-qwen",
        "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    },
    "mistral": {
        "hf_repo": "unsloth/mistral-7b-instruct-v0.3",
        "dataset_file": "mistral_train.jsonl",
        "ollama_name": "aris-mistral",
        "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    },
    "gemma4": {
        "hf_repo": "unsloth/gemma-2-9b-it",
        "dataset_file": "gemma4_train.jsonl",
        "ollama_name": "aris-gemma",
        "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    }
}

def train_model(model_name, dry_run=False):
    if model_name not in MODEL_CONFIGS:
        print(f"Error: Unknown model {model_name}. Available: {list(MODEL_CONFIGS.keys())}")
        return False

    cfg = MODEL_CONFIGS[model_name].copy()
    
    # Overrides for testing on limited laptop resource/speed
    if dry_run:
        print("[DRY-RUN] Overriding base model with a tiny 0.5B model to test the pipeline in seconds...")
        cfg["hf_repo"] = "Qwen/Qwen1.5-0.5B-Chat"
        cfg["target_modules"] = ["q_proj", "v_proj"]

    dataset_path = os.path.join(DATA_DIR, cfg["dataset_file"])
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset {dataset_path} does not exist. Run prepare_data.py first.")
        return False

    print(f"\n=========================================")
    print(f"STARTING FINE-TUNING FOR: {model_name} (Dry-run={dry_run})")
    print(f"Base model: {cfg['hf_repo']}")
    print(f"Dataset: {cfg['dataset_file']}")
    print(f"=========================================\n")

    # Set Hugging Face Token from environment (if loaded via .env)
    hf_token = os.getenv("HF_TOKEN")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token

    # Detect BFloat16 compatibility
    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if use_bf16 else torch.float16
    print(f"Using compute dtype: {compute_dtype} (BFloat16 supported: {use_bf16})")

    # 1. Quantization Configuration (4-bit QLoRA)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True
    )

    print("Loading 4-bit base model...")
    model = AutoModelForCausalLM.from_pretrained(
        cfg["hf_repo"],
        quantization_config=bnb_config,
        device_map="auto",
        token=hf_token
    )
    
    tokenizer = AutoTokenizer.from_pretrained(
        cfg["hf_repo"],
        token=hf_token
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 2. LoRA Config
    peft_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=cfg["target_modules"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 3. Load dataset
    print("Loading training dataset...")
    dataset = load_dataset("json", data_files=dataset_path, split="train")

    def format_prompts(batch):
        # Format dataset to use HF tokenization standard
        formatted = []
        for messages in batch["messages"]:
            # Format using Hugging Face chat templates
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            formatted.append(text)
        return {"text": formatted}

    dataset = dataset.map(format_prompts, batched=True)

    # 4. SFT Configuration
    output_dir = os.path.join(ADAPTERS_DIR, f"{model_name}_checkpoints")
    sft_config = SFTConfig(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=1 if dry_run else 5,
        max_steps=3 if dry_run else 30,  # Fast training run for local iterations
        optim="paged_adamw_8bit",
        bf16=use_bf16,
        fp16=not use_bf16,
        gradient_checkpointing=True,
        report_to="none",
        dataset_text_field="text",
        max_length=512
    )

    # 5. SFTTrainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=sft_config
    )

    print("Running training loop (QLoRA)...")
    trainer.train()

    # Save LoRA adapter weights
    adapter_path = os.path.join(ADAPTERS_DIR, model_name)
    shutil.rmtree(adapter_path, ignore_errors=True)
    trainer.model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"LoRA adapters saved successfully to: {adapter_path}")

    # Clear CUDA memory before merging
    del model
    del trainer
    torch.cuda.empty_cache()

    # 6. Merge weights on CPU to save VRAM
    print("Loading base model on CPU for weight merging...")
    base_model_cpu = AutoModelForCausalLM.from_pretrained(
        cfg["hf_repo"],
        device_map="cpu",
        torch_dtype=torch.float16,
        token=hf_token
    )
    
    print("Merging LoRA adapters into base weights...")
    peft_model = PeftModel.from_pretrained(base_model_cpu, adapter_path)
    merged_model = peft_model.merge_and_unload()

    merged_path = os.path.join(MERGED_DIR, model_name)
    shutil.rmtree(merged_path, ignore_errors=True)
    merged_model.save_pretrained(merged_path)
    tokenizer.save_pretrained(merged_path)
    print(f"Merged model saved successfully to: {merged_path}")

    # Clear memory again
    del base_model_cpu
    del peft_model
    del merged_model
    torch.cuda.empty_cache()

    # 7. Convert merged model to GGUF format
    print("Converting model to GGUF format...")
    gguf_file_path = os.path.join(GGUF_DIR, f"{model_name}.gguf")
    
    # Run llama.cpp conversion script
    python_exe = sys.executable
    cmd = [
        python_exe,
        CONVERTER_PATH,
        merged_path,
        "--outfile",
        gguf_file_path,
        "--outtype",
        "f16"  # Convert to Float16 GGUF (Ollama will handle quantization if needed, or runs f16 directly)
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print(f"GGUF conversion failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        return False
        
    print(f"GGUF file compiled successfully at: {gguf_file_path}")

    # 8. Create Modelfile & Register in Ollama
    modelfile_path = os.path.join(BASE_DIR, f"Modelfile.{model_name}")
    
    # We load the system prompt from the prepared dataset to match Shubh's profile
    with open(dataset_path, "r", encoding="utf-8") as f:
        first_line = json.loads(f.readline())
        system_prompt = first_line["messages"][0]["content"]

    modelfile_content = f"""FROM {gguf_file_path}
TEMPLATE \"\"\"{{{{ if .System }}}}<|start_header_id|>system<|end_header_id|>

{{{{ .System }}}}<|eot_id|>{{{{ end }}}}{{{{ if .Prompt }}}}<|start_header_id|>user<|end_header_id|>

{{{{ .Prompt }}}}<|eot_id|>{{{{ end }}}}<|start_header_id|>assistant<|end_header_id|>

{{{{ .Response }}}}<|eot_id|>\"\"\"
SYSTEM "{system_prompt}"
PARAMETER stop "<|start_header_id|>"
PARAMETER stop "<|end_header_id|>"
PARAMETER stop "<|eot_id|>"
PARAMETER stop "<|reserved_special_token_"
"""
    
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile_content)

    print(f"Registering model '{cfg['ollama_name']}' in Ollama...")
    ollama_cmd = ["ollama", "create", cfg["ollama_name"], "-f", modelfile_path]
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "127.0.0.1:11434"
    res_ollama = subprocess.run(ollama_cmd, capture_output=True, text=True, env=env, encoding="utf-8")
    
    if res_ollama.returncode != 0:
        print(f"Failed to register model in Ollama:\n{res_ollama.stderr}")
        return False

    print(f"SUCCESS! Fine-tuned model '{cfg['ollama_name']}' is registered and ready in Ollama.")
    return True

if __name__ == "__main__":
    import traceback
    
    tb_file = os.path.join(BASE_DIR, "traceback.txt")
    try:
        parser = argparse.ArgumentParser(description="ARIS Model Fine-Tuner")
        parser.add_argument("--model", type=str, required=True, choices=list(MODEL_CONFIGS.keys()), help="Model to fine-tune")
        parser.add_argument("--dry-run", action="store_true", help="Perform a fast pipeline dry-run with a tiny base model")
        args = parser.parse_args()

        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BACKEND_DIR, ".env"))

        success = train_model(args.model, dry_run=args.dry_run)
        if not success:
            with open(tb_file, "w", encoding="utf-8") as f:
                f.write("Failed without exception.")
            sys.exit(1)
    except Exception as e:
        with open(tb_file, "w", encoding="utf-8") as f:
            f.write(f"EXCEPTION:\n{str(e)}\n\nTRACEBACK:\n")
            traceback.print_exc(file=f)
        sys.exit(1)
