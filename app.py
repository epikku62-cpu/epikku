def nai_generate(prompt, width, height, ref_uris=None, strengths=None):
    if not NAI_KEY:
        raise Exception("NOVELAI_API_KEY がありません")
    width, height = nai_size(width, height)
    if width * height > 1216 * 832:
        if width >= height:
            width, height = 1216, 832
        else:
            width, height = 832, 1216
    uc = "lowres, bad anatomy, text, speech bubble, watermark, logo"
    ref_uris = [u for u in (ref_uris or []) if u]
    strengths = strengths or []
    parameters = {
        "params_version": 3,
        "width": width,
        "height": height,
        "scale": 5.0,
        "sampler": "k_euler_ancestral",
        "steps": 23,
        "n_samples": 1,
        "qualityToggle": True,
        "ucPreset": 0,
        "negative_prompt": uc,
        "v4_prompt": {
            "caption": {"base_caption": prompt, "char_captions": []},
            "use_coords": False,
            "use_order": True,
        },
        "v4_negative_prompt": {
            "caption": {"base_caption": uc, "char_captions": []},
            "legacy_uc": False,
        },
    }
    action = "generate"
    if ref_uris:
        parameters["image"] = uri_to_b64(ref_uris[0])
        s = strengths[0] if strengths else 6
        parameters["strength"] = max(0.25, min(0.75, s / 10))
        parameters["noise"] = 0.1
        action = "img2img"
    models = [
        os.environ.get("NOVELAI_MODEL", "").strip(),
        "nai-diffusion-4-5-full",
        "nai-diffusion-4-5-curated",
        "nai-diffusion-4-full",
    ]
    last_err = None
    for model in [m for m in models if m]:
        payload = {
            "input": prompt,
            "model": model,
            "action": action,
            "parameters": parameters,
        }
        for url in NAI_URLS:
            res = requests.post(
                url,
                headers={"Authorization": f"Bearer {NAI_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=180,
            )
            if res.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                    png = zf.read(zf.namelist()[0])
                return "data:image/png;base64," + base64.b64encode(png).decode()
            last_err = f"{model} / {res.status_code}: {res.text[:300]}"
            if "enum" in (res.text or "") and model:
                break
    raise Exception(last_err or "NovelAIの生成に失敗しました")
