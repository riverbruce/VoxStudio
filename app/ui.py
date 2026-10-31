"""Giao diện VoxStudio – thiết kế theo từng bước, dễ dùng cho người không rành kỹ thuật.
Các tuỳ chỉnh chuyên sâu được gom vào mục "Nâng cao" (đóng sẵn)."""
import os
import time
import traceback
from pathlib import Path

import gradio as gr

from . import audio_utils as au
from . import emotion, engine, heartbeat, jobs, lora, updater, voices
from .config import AUDIO_EXTS, OUTPUTS, PRESETS, ROOT, SETTINGS, TEXT_EXTS
from .langs import LANGS, choices as lang_choices, label as lang_label, spaced
from .text_import import read_script
from .vi_normalize import normalize

CSS = """
.gradio-container {max-width: 1180px !important; margin: auto !important;}
.step {border: 1px solid var(--border-color-primary); border-radius: 14px; padding: 14px 16px !important;
       background: var(--background-fill-secondary);}
.step h3 {margin: 0 0 6px 0 !important;}
.bigbtn button, button.bigbtn {font-size: 1.15rem !important; padding: 14px !important; border-radius: 12px !important;}
.hint {opacity: .8; font-size: .92rem;}
footer {display: none !important;}
.updbar {border: 2px solid #f59e0b; border-radius: 12px; padding: 10px 14px !important; background: rgba(245,158,11,.08);}
"""
HEAD = ""

PRESET_NAMES = {
    "Short / TikTok / Reels": "📱 Short / TikTok / Reels (nhanh, sub 3–5 từ)",
    "YouTube dài / Podcast": "▶️ YouTube dài / Podcast",
    "Sách nói / Truyện (chậm, ấm)": "📖 Sách nói / Truyện (chậm, ấm)",
}
PRESET_CHOICES = [(v, k) for k, v in PRESET_NAMES.items()]
MODE_CHOICES = [("Giống nhất (Ultimate)", "ultimate"), ("Chỉ lấy âm sắc (Reference)", "reference")]
TEST_TEXT = {
    "vi": "Xin chào các bạn, đây là giọng đọc thử nghiệm. Chúc các bạn một ngày thật vui!",
    "en": "Hello everyone, this is a quick voice test. Have a wonderful day!",
    "zh": "大家好，这是一段语音测试。祝大家今天愉快！",
    "ja": "皆さん、こんにちは。これは音声のテストです。素敵な一日を！",
    "ko": "안녕하세요, 음성 테스트입니다. 좋은 하루 보내세요!",
    "th": "สวัสดีทุกคน นี่คือการทดสอบเสียง ขอให้มีวันที่ดีนะ",
}


def _err(e):
    engine.log(traceback.format_exc())
    from .friendly import humanize
    return humanize(e)


def vchoices(lang=None):
    return voices.list_voices(lang)


def unit_label(lang):
    return "Số **từ** mỗi dòng phụ đề" if spaced(lang) else "Số **ký tự** mỗi dòng phụ đề (ngôn ngữ không có dấu cách)"


def build_ui():
    with gr.Blocks(title="VoxStudio") as demo:
        _v = updater.local_info().get("version", "?")
        gr.Markdown(f"# 🎙️ VoxStudio <span class='hint' style='font-size:.9rem'>v{_v}</span>\n"
                    "<span class='hint'>Clone giọng & đọc kịch bản thành audio + phụ đề · chạy hoàn toàn trên máy bạn</span>")
        with gr.Row(visible=False, elem_classes="updbar") as upd_row:
            upd_md = gr.Markdown()
            upd_btn = gr.Button("⬇️ Cập nhật ngay", variant="primary", scale=0, min_width=180)
        upd_msg = gr.Markdown()
        hb_timer = gr.Timer(20.0)
        hb_timer.tick(heartbeat.beat, None, None, show_progress="hidden")

        # =============================================================== TAB 1: TẠO GIỌNG
        with gr.Tab("🎤 Tạo giọng"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=1, elem_classes="step"):
                    gr.Markdown("### ① Thông tin giọng")
                    v_name = gr.Textbox(label="Đặt tên giọng", placeholder="VD: Nam trầm kể chuyện")
                    v_ref = gr.Dropdown(lang_choices(), value="vi", label="Giọng mẫu đang nói tiếng gì?")
                    v_tgt = gr.Dropdown(lang_choices(), value="vi", label="Lưu giọng này để đọc tiếng gì?",
                                        info="Thường giống ngôn ngữ giọng mẫu. Có thể chọn khác để đọc chéo ngôn ngữ.")
                with gr.Column(scale=1, elem_classes="step"):
                    gr.Markdown("### ② Tải giọng mẫu")
                    gr.Markdown("<span class='hint'>Nhận mọi file âm thanh/video. **Nên dùng WAV hoặc MP3**, giọng rõ, "
                                "không nhạc nền. Càng nhiều đoạn (mỗi đoạn 5–20 giây) càng tốt.</span>")
                    v_files = gr.File(file_count="multiple", file_types=AUDIO_EXTS, label="Kéo thả file vào đây")
                    v_dn = gr.Checkbox(False, label="Giọng mẫu có tiếng ồn → bật khử nhiễu")
            v_go = gr.Button("✨ Tạo giọng", variant="primary", elem_classes="bigbtn")
            v_msg = gr.Markdown()

            with gr.Column(elem_classes="step"):
                gr.Markdown("### ③ Giọng đã lưu · nghe thử")
                with gr.Row():
                    t_voice = gr.Dropdown(vchoices(), label="Giọng đã lưu", scale=3)
                    t_rf = gr.Button("🔄", scale=0, min_width=50)
                    t_del = gr.Button("🗑️ Xoá giọng này", variant="stop", scale=1)
                with gr.Group(visible=False) as del_box:
                    del_md = gr.Markdown()
                    with gr.Row():
                        del_no = gr.Button("Huỷ")
                        del_yes = gr.Button("✅ Đúng, xoá giọng này", variant="stop")
                del_target = gr.State(None)
                with gr.Row():
                    t_text = gr.Textbox(TEST_TEXT["vi"], label="Câu đọc thử", scale=4)
                    t_btn = gr.Button("▶️ Nghe thử", variant="primary", scale=1)
                with gr.Row():
                    t_emo = gr.Dropdown([c for c in emotion.choices() if c[1] != "auto"], value="natural",
                                        label="Cảm xúc", scale=2)
                    t_int = gr.Radio(list(emotion.INTENSITY), value="Vừa", label="Mức độ", scale=1)
                    t_cus = gr.Textbox(label="Chỉ dẫn tự viết (tiếng Anh tốt nhất, VD: tired, sleepy voice)", scale=3,
                                       visible=False)
                t_audio = gr.Audio(label="Kết quả", type="filepath")
                with gr.Accordion("♻️ Giọng đã xoá (khôi phục)", open=False):
                    with gr.Row():
                        tr_dd = gr.Dropdown(voices.list_trash(), label="Thùng rác", scale=3)
                        tr_restore = gr.Button("↩️ Khôi phục", scale=1)
                        tr_sure = gr.Checkbox(False, label="Tôi chắc chắn", scale=1)
                        tr_purge = gr.Button("❌ Xoá vĩnh viễn", variant="stop", scale=1)

            # ---------------- nâng cao
            with gr.Accordion("⚙️ Quản lý giọng đã lưu (nâng cao)", open=False):
                gr.Markdown("<span class='hint'>Đang quản lý giọng được chọn ở ô <b>Giọng đã lưu</b> phía trên.</span>")
                m_voice = t_voice
                m_info = gr.Markdown()
                with gr.Row():
                    m_ref = gr.Dropdown(lang_choices(), label="Ngôn ngữ giọng mẫu")
                    m_tgt = gr.Dropdown(lang_choices(), label="Dùng để đọc tiếng")
                    m_mode = gr.Radio(MODE_CHOICES, label="Kiểu clone")
                    m_save = gr.Button("💾 Lưu")
                with gr.Tab("Đoạn mẫu"):
                    m_files = gr.File(file_count="multiple", file_types=AUDIO_EXTS, label="Thêm đoạn mẫu")
                    with gr.Row():
                        m_dn = gr.Checkbox(False, label="Khử nhiễu")
                        m_add = gr.Button("➕ Thêm & tạo lại tham chiếu")
                    m_df = gr.Dataframe(headers=["file", "nguồn", "giây", "điểm", "SNR dB", "dùng"], interactive=False,
                                        label="Điểm cao = sạch, rõ. Tắt các đoạn kém rồi tạo lại tham chiếu.")
                    with gr.Row():
                        m_clip = gr.Textbox(label="Tên đoạn (VD 003.wav)")
                        m_toggle = gr.Button("Bật/Tắt đoạn")
                        m_split = gr.Button("✂️ Cắt đoạn dài")
                        m_tsec = gr.Slider(8, 30, 20, step=1, label="Độ dài tham chiếu (giây)")
                        m_build = gr.Button("⭐ Tạo lại tham chiếu")
                with gr.Tab("Tham chiếu"):
                    with gr.Row():
                        m_ra = gr.Audio(label="reference.wav – ghép từ đoạn tốt nhất", type="filepath")
                        m_pa = gr.Audio(label="prompt.wav – đoạn đơn tốt nhất", type="filepath")
                    m_pt = gr.Textbox(label="Lời của prompt.wav (sửa nếu nhận dạng sai rồi bấm Lưu)", lines=2)
                with gr.Tab("Đổi tên"):
                    with gr.Row():
                        m_new = gr.Textbox(label="Tên mới")
                        m_ren = gr.Button("Đổi tên")
                with gr.Tab("📤 Chia sẻ giọng sang máy khác"):
                    gr.Markdown("<span class='hint'>Xuất giọng đang chọn thành 1 file <b>.voxvoice</b> (gồm đoạn mẫu, tham chiếu "
                                "và bản huấn luyện nếu có) → gửi qua Zalo/Drive/USB → máy kia bấm <b>Nhập giọng</b>.</span>")
                    with gr.Row():
                        ex_btn = gr.Button("📤 Xuất giọng đang chọn")
                        ex_file = gr.File(label="File giọng để gửi đi", interactive=False)
                    with gr.Row():
                        im_file = gr.File(label="📥 Thả file .voxvoice nhận được vào đây", file_types=[".voxvoice", ".zip"])
                        im_btn = gr.Button("📥 Nhập giọng", variant="primary")
                with gr.Tab("🧠 Huấn luyện giọng (tuỳ chọn)"):
                    gr.Markdown("<span class='hint'><b>Huấn luyện</b> = dạy riêng cho máy giọng này để đọc <b>giống hơn nữa</b>. "
                                "Không bắt buộc. Cần <b>từ 10 phút</b> giọng nói sạch, mất khoảng <b>30–90 phút</b>; "
                                "trong lúc đó tạm thời chưa đọc kịch bản được.</span>")
                    l_info = gr.Markdown()
                    with gr.Row():
                        l_files = gr.File(file_count="multiple", file_types=AUDIO_EXTS, scale=3,
                                          label="① Thêm âm thanh giọng này (file dài vài phút tới 1 tiếng · WAV/MP3)")
                        with gr.Column(scale=1):
                            l_dn = gr.Checkbox(False, label="Có tiếng ồn → khử nhiễu")
                            l_add = gr.Button("⬆️ Thêm vào", variant="secondary")
                    with gr.Row():
                        l_start = gr.Button("② 🚀 Bắt đầu huấn luyện", variant="primary", elem_classes="bigbtn", scale=3)
                        l_stop = gr.Button("⏹️ Dừng", variant="stop", scale=1)
                    l_status = gr.Markdown()
                    l_on = gr.Checkbox(False, label="③ Dùng bản huấn luyện cho giọng này")
                    with gr.Accordion("Tuỳ chỉnh nâng cao", open=False):
                        with gr.Row():
                            l_clips = gr.Checkbox(True, label="Dùng cả các đoạn mẫu lúc tạo giọng")
                            l_it = gr.Number(1000, label="Số bước (nhiều = lâu hơn)", precision=0)
                            l_lr = gr.Number(1e-4, label="Tốc độ học")
                            l_rank = gr.Dropdown([8, 16, 32], value=32, label="Rank (giảm nếu báo hết bộ nhớ)")
                    with gr.Accordion("Chi tiết kỹ thuật (cho người hỗ trợ)", open=False):
                        l_log = gr.Textbox(label="Log", lines=12, max_lines=12)
                    l_timer = gr.Timer(4.0)
                m_msg = gr.Markdown()

            # ---------------- logic tab 1
            def all_voice_updates(sel=None):
                c = vchoices()
                if sel not in [v for _, v in c]:
                    sel = None
                return gr.update(choices=c, value=sel)

            v_ref.change(lambda r: r, v_ref, v_tgt)

            def on_create(name, rl, tl, files, dn):
                if not name or not name.strip():
                    return "❌ Hãy đặt tên giọng.", gr.update(), gr.update()
                if not files:
                    return "❌ Hãy tải ít nhất 1 file giọng mẫu.", gr.update(), gr.update()
                try:
                    logs = []
                    vid = voices.quick_create(name.strip(), rl, tl, files, dn, log=logs.append)
                    m = voices.load_meta(vid)
                    good = sum(1 for c in m["clips"] if c["score"] >= 60)
                    tip = "" if good else "\n\n⚠️ Chất lượng mẫu thấp – nên dùng file sạch hơn hoặc bật khử nhiễu."
                    msg = (f"✅ Đã lưu giọng **{name}** · mẫu: {lang_label(rl)} · đọc: {lang_label(tl)} · "
                           f"{len(m['clips'])} đoạn, tham chiếu {m['reference']['dur']}s{tip}\n\nGiờ hãy bấm **Nghe thử** bên dưới.")
                    return msg, all_voice_updates(vid), TEST_TEXT.get(tl, TEST_TEXT["en"])
                except Exception as e:
                    return _err(e), gr.update(), gr.update()

            v_go.click(on_create, [v_name, v_ref, v_tgt, v_files, v_dn], [v_msg, t_voice, t_text])

            def on_test(vid, txt, emo, inten, cus):
                if not vid:
                    return None, "❌ Chọn giọng trước."
                if lora.is_busy():
                    return None, "⏳ Card đồ hoạ đang bận **huấn luyện giọng**. Đợi huấn luyện xong (hoặc bấm Dừng) rồi nghe thử."
                try:
                    m = voices.load_meta(vid)
                    lang = m.get("target_lang", "vi")
                    vin = voices.voice_inputs(vid, read_lang=lang)
                    style = emotion.instruction(emo, inten, cus)
                    body = normalize(txt, lang)
                    if style:
                        body = f"({style}){body}"
                        vin = dict(vin, ref_wav=vin["ref_wav"] or vin["prompt_wav"], prompt_wav=None, prompt_text=None)
                    t = time.time()
                    x, sr = engine.synthesize(body, **vin, cfg_value=m.get("cfg_value", 2.0),
                                              timesteps=m.get("timesteps", 10), seed=SETTINGS.get("seed"))
                    out = au.save_wav(au.tmp_path(), x, sr)
                    return str(out), f"✅ {len(x) / sr:.1f}s audio · {time.time() - t:.1f}s"
                except Exception as e:
                    return None, _err(e)

            t_btn.click(on_test, [t_voice, t_text, t_emo, t_int, t_cus], [t_audio, v_msg])
            t_emo.change(lambda e: gr.update(visible=e == "custom"), t_emo, t_cus)
            t_voice.change(lambda v: TEST_TEXT.get(voices.load_meta(v).get("target_lang", "vi"), TEST_TEXT["en"]) if v else gr.update(),
                           t_voice, t_text)

            def view(vid):
                if not vid:
                    return "", None, None, None, None, "", [], None
                m = voices.load_meta(vid)
                d = voices.voice_dir(vid)
                total = sum(c.get("dur", 0) for c in m.get("clips", []) if c.get("enabled", True))
                info = (f"**{m.get('name')}** · mẫu {lang_label(m.get('ref_lang', 'vi'))} → đọc {lang_label(m.get('target_lang', 'vi'))}"
                        f" · {len(m.get('clips', []))} đoạn ({total:.0f}s)"
                        + (f" · LoRA {'BẬT' if m.get('use_lora') else 'tắt'}" if m.get("lora") else ""))
                ra = str(d / "reference.wav") if (d / "reference.wav").exists() else None
                pa = str(d / "prompt.wav") if (d / "prompt.wav").exists() else None
                return (info, m.get("ref_lang", "vi"), m.get("target_lang", "vi"), m.get("mode", "ultimate"), ra,
                        (m.get("prompt") or {}).get("text", ""), voices.clips_table(vid), pa)

            mv_out = [m_info, m_ref, m_tgt, m_mode, m_ra, m_pt, m_df, m_pa]
            m_voice.change(view, m_voice, mv_out)
            t_rf.click(lambda v: all_voice_updates(v), t_voice, t_voice)

            # ---- xoá giọng: bấm Xoá -> hiện hộp xác nhận ghi rõ giọng nào -> chỉ xoá đúng giọng đã ghi
            def ask_delete(vid):
                if not vid:
                    return gr.update(visible=False), "", None, "❌ Chưa chọn giọng nào để xoá."
                try:
                    info = voices.describe(vid)
                except Exception:
                    return gr.update(visible=False), "", None, "❌ Giọng này không còn tồn tại, bấm 🔄."
                return (gr.update(visible=True), f"### ⚠️ Xoá giọng này?\n{info}\n\n"
                        "<span class='hint'>Giọng sẽ vào thùng rác, khôi phục được ở mục ♻️ bên dưới.</span>",
                        vid, "")

            def do_delete(target, lang, show_all):
                hide = gr.update(visible=False)
                if not target:
                    return hide, None, all_voice_updates(None), gr.update(), gr.update(), "❌ Không có giọng nào được xác nhận."
                if jobs.RUNNER.busy():
                    try:
                        if jobs.load_job(jobs.RUNNER.state["job"])["voice"] == target:
                            return hide, None, gr.update(), gr.update(), gr.update(), "❌ Giọng này đang được dùng để đọc, hãy dừng trước."
                    except Exception:
                        pass
                try:
                    name = voices.load_meta(target).get("name", target)
                    voices.delete_voice(target)
                    msg = f"🗑️ Đã xoá giọng **{name}** (`{target}`). Có thể khôi phục ở mục ♻️."
                except Exception as e:
                    msg = _err(e)
                sv = gr.update(choices=vchoices(None if show_all else lang), value=None)
                return (hide, None, all_voice_updates(None), sv, gr.update(choices=voices.list_trash(), value=None), msg)

            t_del.click(ask_delete, t_voice, [del_box, del_md, del_target, v_msg])
            del_no.click(lambda: (gr.update(visible=False), None, "Đã huỷ xoá."), None, [del_box, del_target, v_msg])
            t_voice.change(lambda v: (gr.update(visible=False), None), t_voice, [del_box, del_target])

            def on_restore(tid):
                if not tid:
                    return gr.update(), gr.update(), "❌ Chọn giọng trong thùng rác."
                try:
                    vid = voices.restore_voice(tid)
                    return (gr.update(choices=voices.list_trash(), value=None), all_voice_updates(vid),
                            f"↩️ Đã khôi phục giọng `{vid}`.")
                except Exception as e:
                    return gr.update(), gr.update(), _err(e)

            def on_purge(tid, sure):
                if not tid:
                    return gr.update(), False, "❌ Chọn giọng trong thùng rác."
                if not sure:
                    return gr.update(), False, "⚠️ Tích ô 'Tôi chắc chắn' trước khi xoá vĩnh viễn."
                try:
                    voices.purge_voice(tid)
                    return gr.update(choices=voices.list_trash(), value=None), False, "❌ Đã xoá vĩnh viễn."
                except Exception as e:
                    return gr.update(), False, _err(e)

            tr_restore.click(on_restore, tr_dd, [tr_dd, t_voice, v_msg])
            tr_purge.click(on_purge, [tr_dd, tr_sure], [tr_dd, tr_sure, v_msg])

            def on_msave(vid, rl, tl, mode, pt):
                m = voices.load_meta(vid)
                m.update({"ref_lang": rl, "target_lang": tl, "mode": mode})
                if m.get("prompt"):
                    m["prompt"]["text"] = pt.strip()
                voices.save_meta(vid, m)
                return "💾 Đã lưu", all_voice_updates(vid)

            m_save.click(on_msave, [m_voice, m_ref, m_tgt, m_mode, m_pt], [m_msg, t_voice])

            def wrap(fn):
                def inner(vid, *a):
                    try:
                        r = fn(vid, *a)
                        return (*view(vid), r or "✅ Xong")
                    except Exception as e:
                        return (*view(vid), _err(e))
                return inner

            def _add(vid, files, dn):
                logs = []
                voices.add_clips(vid, files, dn, log=logs.append)
                voices.build_reference(vid, log=logs.append)
                return "✅ " + " | ".join(logs)

            m_add.click(wrap(_add), [m_voice, m_files, m_dn], mv_out + [m_msg])
            m_toggle.click(wrap(lambda v, c: voices.toggle_clip(v, c.strip())), [m_voice, m_clip], mv_out + [m_msg])
            m_split.click(wrap(lambda v, c: f"✂️ {voices.split_long_clip(v, c.strip())} đoạn"), [m_voice, m_clip], mv_out + [m_msg])
            m_build.click(wrap(lambda v, t: (voices.build_reference(v, target_sec=t), "⭐ Đã tạo lại tham chiếu")[1]),
                          [m_voice, m_tsec], mv_out + [m_msg])
            def on_rename(v, n):
                if not v or not n.strip():
                    return "❌ Chọn giọng và nhập tên mới.", gr.update()
                voices.rename_voice(v, n.strip())
                return f"✏️ Đã đổi tên thành **{n.strip()}**", all_voice_updates(v)

            m_ren.click(on_rename, [m_voice, m_new], [m_msg, t_voice])

            def on_export(vid):
                if not vid:
                    return None, "❌ Chọn giọng ở ô **Giọng đã lưu** trước."
                try:
                    f = voices.export_voice(vid)
                    return str(f), f"📤 Đã xuất **{f.name}** ({f.stat().st_size / 1e6:.1f} MB). Bấm vào file để tải về rồi gửi đi."
                except Exception as e:
                    return None, _err(e)

            def on_import(f):
                if not f:
                    return gr.update(), "❌ Chưa chọn file .voxvoice."
                try:
                    vid = voices.import_voice(f)
                    return all_voice_updates(vid), f"📥 Đã nhập giọng **{voices.load_meta(vid).get('name')}**. Bấm Nghe thử để kiểm tra."
                except Exception as e:
                    return gr.update(), _err(e)

            ex_btn.click(on_export, m_voice, [ex_file, m_msg])
            im_btn.click(on_import, im_file, [t_voice, m_msg])

            def l_add_fn(vid, files, dn):
                if not vid:
                    return "❌ Hãy chọn giọng ở ô **Giọng đã lưu** phía trên trước.", ""
                if not files:
                    return "❌ Chưa chọn file nào.", lora.training_summary(vid)
                try:
                    logs = []
                    lora.add_training_files(vid, files, dn, log=logs.append)
                    return "✅ Đã thêm: " + " · ".join(logs), lora.training_summary(vid)
                except Exception as e:
                    return _err(e), lora.training_summary(vid)

            l_add.click(l_add_fn, [m_voice, l_files, l_dn], [l_status, l_info])

            def l_view(vid):
                md, log = lora.friendly_status(vid)
                on = bool(vid) and bool(voices.load_meta(vid).get("use_lora"))
                return lora.training_summary(vid), md, log, on

            m_voice.change(l_view, m_voice, [l_info, l_status, l_log, l_on])

            def l_start_fn(vid, it, lr_, rk, uc):
                try:
                    if jobs.RUNNER.busy():
                        return "❌ Đang đọc kịch bản. Hãy đợi xong hoặc tạm dừng rồi mới huấn luyện."
                    lora.start_all(vid, int(it), float(lr_), int(rk), bool(uc))
                    return "### ⏳ Đang bắt đầu..."
                except Exception as e:
                    return _err(e)

            l_start.click(l_start_fn, [m_voice, l_it, l_lr, l_rank, l_clips], l_status)
            l_stop.click(lambda v: (lora.stop_training(v), "### ⏸️ Đã dừng huấn luyện.")[1], m_voice, l_status)

            def l_tick(vid):
                if not vid:
                    return gr.update(), gr.update(), gr.update()
                md, log = lora.friendly_status(vid)
                on = bool(voices.load_meta(vid).get("use_lora"))
                return md, log, on

            l_timer.tick(l_tick, m_voice, [l_status, l_log, l_on])

            def l_on_fn(vid, on):
                if not vid:
                    return ""
                m = voices.load_meta(vid)
                if on and not m.get("lora"):
                    return "⚠️ Giọng này chưa có bản huấn luyện nào — hãy huấn luyện trước."
                m["use_lora"] = bool(on) and bool(m.get("lora"))
                voices.save_meta(vid, m)
                return "✅ Đang dùng bản huấn luyện." if m["use_lora"] else "Đã tắt bản huấn luyện (dùng giọng clone thường)."

            l_on.input(l_on_fn, [m_voice, l_on], m_msg)

        # =============================================================== TAB 2: ĐỌC KỊCH BẢN
        with gr.Tab("📜 Đọc kịch bản"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, elem_classes="step"):
                    gr.Markdown("### ① Nội dung")
                    s_file = gr.File(file_types=TEXT_EXTS, label="Thả file kịch bản (txt, srt, docx, pdf, json, epub, csv...) hoặc dán chữ bên dưới")
                    s_text = gr.Textbox(label="Nội dung", lines=10, max_lines=25, placeholder="Dán kịch bản vào đây...")
                    s_info = gr.Markdown()
                with gr.Column(scale=2):
                    with gr.Column(elem_classes="step"):
                        gr.Markdown("### ② Giọng & ngôn ngữ")
                        s_lang = gr.Dropdown(lang_choices(), value="vi", label="Đọc bằng tiếng")
                        s_voice = gr.Dropdown(vchoices("vi"), label="Giọng đọc (đã lưu cho ngôn ngữ này)")
                        s_all = gr.Checkbox(False, label="Hiện cả giọng của ngôn ngữ khác (đọc chéo)")
                    with gr.Column(elem_classes="step"):
                        gr.Markdown("### ③ Loại video & cảm xúc")
                        s_preset = gr.Radio(PRESET_CHOICES, value="YouTube dài / Podcast", show_label=False)
                        s_emo = gr.Dropdown(emotion.choices(), value="natural", label="Cảm xúc giọng đọc")
                        s_int = gr.Radio(list(emotion.INTENSITY), value="Vừa", label="Mức độ cảm xúc")
                        s_cus = gr.Textbox(label="Chỉ dẫn tự viết (tiếng Anh tốt nhất, VD: tired, sleepy voice)",
                                           visible=False)
                        gr.Markdown("<span class='hint'>💡 Đổi cảm xúc giữa bài: gõ thẻ vào kịch bản, VD "
                                    "<code>[buồn]</code> <code>[vui]</code> <code>[hồi hộp]</code> <code>[thì thầm]</code> "
                                    "<code>[kể chuyện]</code> <code>[bình thường]</code> hoặc "
                                    "<code>[style: tired, sleepy voice]</code>. Thẻ có hiệu lực tới thẻ kế tiếp.</span>")
                    with gr.Column(elem_classes="step"):
                        gr.Markdown("### ④ Phụ đề SRT")
                        sub_n = gr.Slider(1, 20, 10, step=1, label="Số từ mỗi dòng phụ đề")
                        with gr.Row():
                            sub_l = gr.Radio([("1 dòng", 1), ("2 dòng", 2)], value=1, label="Số dòng mỗi khung")
                            sub_p = gr.Checkbox(False, label="Bỏ dấu câu cuối dòng")
            s_go = gr.Button("🎬 Tạo audio + phụ đề", variant="primary", elem_classes="bigbtn")
            s_prog = gr.Markdown()
            with gr.Row():
                s_audio = gr.Audio(label="Nghe kết quả", type="filepath")
                s_files = gr.File(label="Tải về: WAV · MP3 · SRT", file_count="multiple")
            with gr.Row():
                s_pause = gr.Button("⏸️ Tạm dừng")
                s_resub = gr.Button("🔤 Xuất lại phụ đề theo cài đặt mới (không đọc lại)")
                s_open = gr.Button("📂 Mở thư mục kết quả")

            with gr.Accordion("⚙️ Tuỳ chỉnh nâng cao", open=False):
                with gr.Row():
                    a_speed = gr.Slider(0.8, 1.3, 1.0, step=0.01, label="Tốc độ đọc")
                    a_ps = gr.Slider(0.1, 1.0, 0.35, step=0.05, label="Nghỉ giữa câu (s)")
                    a_pp = gr.Slider(0.3, 2.0, 0.75, step=0.05, label="Nghỉ giữa đoạn (s)")
                    a_lufs = gr.Slider(-24, -10, -14, step=0.5, label="Âm lượng chuẩn LUFS (YouTube/TikTok -14)")
                with gr.Row():
                    sub_d = gr.Slider(1.0, 10.0, 5.0, step=0.5, label="Thời lượng tối đa mỗi khung sub (s)")
                    a_chars = gr.Slider(80, 400, 240, step=10, label="Độ dài mỗi đoạn đọc (ký tự)")
                    a_mode = gr.Radio([("Theo giọng", "")] + MODE_CHOICES, value="", label="Kiểu clone")
                with gr.Row():
                    a_cfg = gr.Slider(1.0, 4.0, 2.0, step=0.1, label="Bám giọng mẫu (CFG)")
                    a_ts = gr.Slider(4, 30, 10, step=1, label="Độ mịn (steps) – cao thì chậm")
                    a_seed = gr.Number(SETTINGS.get("seed", 1234), label="Seed", precision=0)
                    a_retry = gr.Slider(1, 5, 3, step=1, label="Sinh lại tối đa khi lỗi")
                with gr.Row():
                    a_norm = gr.Checkbox(True, label="Chuẩn hoá số/ngày/viết tắt")
                    a_wq = gr.Checkbox(False, label="Whisper nghe lại kiểm tra lời (chậm hơn)")
                    a_cer = gr.Slider(0.05, 0.6, 0.25, step=0.05, label="Ngưỡng sai lời")
                    o_wav = gr.Checkbox(True, label="WAV")
                    o_mp3 = gr.Checkbox(True, label="MP3")
                    o_chap = gr.Checkbox(False, label="Tách file theo chương")

            cur_job = gr.State(None)

            def on_file(f):
                if not f:
                    return gr.update(), ""
                try:
                    t = read_script(f)
                    return t, f"📄 {Path(f).name}"
                except Exception as e:
                    return gr.update(), _err(e)

            def on_text(t, lang):
                if not t:
                    return ""
                from .langs import cps
                mins = len(t) / cps(lang) / 60
                return f"{len(t):,} ký tự · ước tính **~{mins:.1f} phút** audio · thời gian tạo ~{mins * 1.3:.0f} phút"

            s_file.change(on_file, s_file, [s_text, s_info])
            s_text.change(on_text, [s_text, s_lang], s_info)

            def on_lang(lang, show_all, cur):
                c = vchoices(None if show_all else lang)
                vals = [v for _, v in c]
                return (gr.update(choices=c, value=cur if cur in vals else (vals[0] if vals else None)),
                        gr.update(label=unit_label(lang).replace("**", ""),
                                  maximum=20 if spaced(lang) else 40))

            s_lang.change(on_lang, [s_lang, s_all, s_voice], [s_voice, sub_n])
            s_emo.change(lambda e: gr.update(visible=e == "custom"), s_emo, s_cus)
            s_all.change(on_lang, [s_lang, s_all, s_voice], [s_voice, sub_n])

            def on_preset(p, lang):
                v = PRESETS[p]
                sb = v["sub"]
                n = sb["per_line"] if spaced(lang) else sb["per_line"] * 3
                return v["speed"], v["pause_sentence"], v["pause_paragraph"], v["lufs"], v["max_chars"], n, sb["lines"], sb["strip_punct"], sb["max_dur"]

            s_preset.change(on_preset, [s_preset, s_lang],
                            [a_speed, a_ps, a_pp, a_lufs, a_chars, sub_n, sub_l, sub_p, sub_d])

            def sub_dict(n, l, p, d):
                return {"per_line": int(n), "lines": int(l), "strip_punct": bool(p), "max_dur": float(d)}

            def on_go(text, lang, vid, preset, emo, inten, cus, n, l, p, d, spd, ps, pp, lufs, chars, mode, cfg, ts, seed, retry, norm,
                      wq, cthr, wav, mp3, chap):
                try:
                    if not text or not text.strip():
                        return None, "❌ Chưa có nội dung."
                    if not vid:
                        return None, "❌ Chưa chọn giọng. Hãy tạo giọng ở tab 🎤 trước."
                    if jobs.RUNNER.busy():
                        return None, "❌ Đang có một bản đang chạy, hãy đợi hoặc tạm dừng."
                    if lora.is_busy():
                        return None, "⏳ Card đồ hoạ đang bận **huấn luyện giọng**. Đợi xong (hoặc dừng huấn luyện) rồi đọc."
                    first = text.strip().split("\n")[0][:40]
                    name = time.strftime("%m%d_%H%M_") + first
                    opts = {"lang": lang, "max_chars": int(chars), "speed": float(spd), "lufs": float(lufs),
                            "pause_sentence": float(ps), "pause_paragraph": float(pp), "pause_chapter": float(pp) * 2,
                            "cfg_value": float(cfg), "timesteps": int(ts), "seed": int(seed), "normalize": bool(norm),
                            "out_wav": bool(wav), "out_mp3": bool(mp3) or not wav, "per_chapter": bool(chap),
                            "sub": sub_dict(n, l, p, d), "emotion": emo, "intensity": inten,
                            "emotion_custom": cus or ""}
                    jid = jobs.create_job(name, text, vid, preset, mode or None, opts)
                    jobs.RUNNER.start(jid, whisper_qc=bool(wq), cer_thr=float(cthr), max_retry=int(retry))
                    m = voices.load_meta(vid)
                    note = ""
                    if lang != m.get("ref_lang", "vi"):
                        note = (f"\n\nℹ️ Giọng mẫu là {lang_label(m.get('ref_lang', 'vi'))} nhưng đọc {lang_label(lang)} "
                                "→ tự dùng chế độ 'Chỉ lấy âm sắc' để phát âm đúng.")
                    return jid, "🚀 Đã bắt đầu..." + note
                except Exception as e:
                    return None, _err(e)

            s_go.click(on_go, [s_text, s_lang, s_voice, s_preset, s_emo, s_int, s_cus, sub_n, sub_l, sub_p, sub_d, a_speed, a_ps, a_pp,
                               a_lufs, a_chars, a_mode, a_cfg, a_ts, a_seed, a_retry, a_norm, a_wq, a_cer,
                               o_wav, o_mp3, o_chap], [cur_job, s_prog])

            def outputs_of(jid):
                if not jid:
                    return None, None
                o = jobs.load_job(jid).get("outputs", {})
                files = [o[k] for k in ("mp3", "wav", "srt") if k in o and Path(o[k]).exists()]
                audio = o.get("mp3") or o.get("wav")
                return (audio if audio and Path(audio).exists() else None), (files or None)

            def progress_text(jid):
                st = jobs.RUNNER.state
                if st["running"] and st["job"] == jid:
                    pct = 100 * st["done"] / max(1, st["total"])
                    bar = "█" * int(pct / 4) + "░" * (25 - int(pct / 4))
                    return f"⏳ `{bar}` **{pct:.0f}%** · {st['done']}/{st['total']} đoạn · còn ~{st['eta']}\n\n<span class='hint'>{st['msg']}</span>"
                if jid:
                    j = jobs.load_job(jid)
                    if j["status"] == "done":
                        flags = sum(1 for c in j["chunks"] if c["status"] == "flag")
                        extra = f" · ⚠️ {flags} đoạn nên nghe lại (tab Dự án)" if flags else ""
                        return f"✅ **Xong!** Tổng {j.get('total_sec', 0) / 60:.1f} phút audio{extra}"
                    return f"Trạng thái: {j['status']} · {(j.get('log') or [''])[-1]}"
                return gr.update()

            def tick(jid):
                txt = progress_text(jid)
                if jid and not jobs.RUNNER.busy():
                    j = jobs.load_job(jid)
                    if j["status"] == "done":
                        a, f = outputs_of(jid)
                        return txt, a, f, None   # đưa kết quả ra và ngừng theo dõi
                return txt, gr.update(), gr.update(), jid

            timer = gr.Timer(2.0)
            timer.tick(tick, cur_job, [s_prog, s_audio, s_files, cur_job])
            s_pause.click(lambda: (jobs.RUNNER.stop(), "⏸️ Sẽ dừng sau đoạn hiện tại. Tiếp tục ở tab 🗂️ Dự án.")[1], None, s_prog)

            def on_resub(n, l, p, d):
                lst = jobs.list_jobs()
                if not lst:
                    return "❌ Chưa có dự án nào.", None
                jid = lst[0][1]
                try:
                    jobs.export_srt_only(jid, sub_dict(n, l, p, d))
                    return "🔤 Đã xuất lại phụ đề cho dự án gần nhất.", outputs_of(jid)[1]
                except Exception as e:
                    return _err(e), None

            s_resub.click(on_resub, [sub_n, sub_l, sub_p, sub_d], [s_prog, s_files])
            s_open.click(lambda: (os.startfile(str(OUTPUTS)) if os.name == "nt" else None, "📂 Đã mở")[1], None, s_prog)

        # =============================================================== TAB 3: DỰ ÁN
        with gr.Tab("🗂️ Dự án"):
            gr.Markdown("<span class='hint'>Mọi lần đọc đều được lưu tại đây. Bị tắt máy / dừng giữa chừng → chọn dự án và bấm "
                        "**Chạy tiếp**. Có thể nghe & sửa từng đoạn.</span>")
            with gr.Row():
                p_job = gr.Dropdown(jobs.list_jobs(), label="Dự án", scale=4)
                p_rf = gr.Button("🔄", scale=0, min_width=50)
                p_run = gr.Button("▶️ Chạy tiếp", scale=1)
                p_stop = gr.Button("⏸️ Dừng", scale=1)
                p_exp = gr.Button("🧩 Ghép & xuất lại", scale=1)
            p_prog = gr.Markdown()
            with gr.Row():
                p_audio = gr.Audio(label="Kết quả", type="filepath")
                p_files = gr.File(label="Tải về", file_count="multiple")
            p_df = gr.Dataframe(headers=["#", "TT", "cảm xúc", "giây", "lần", "ghi chú", "văn bản"], interactive=False, wrap=True,
                                max_height=380)
            with gr.Row():
                p_idx = gr.Number(1, label="Đoạn số", precision=0)
                p_load = gr.Button("🎧 Mở đoạn")
                p_regen = gr.Button("🔁 Sửa & đọc lại đoạn này", variant="primary")
            p_text = gr.Textbox(label="Văn bản đoạn (gõ thẻ như [buồn] ở đầu để đổi cảm xúc riêng đoạn này)", lines=3)
            p_caudio = gr.Audio(label="Âm thanh đoạn", type="filepath")

            def table(jid):
                if not jid:
                    return []
                icon = {"done": "✅", "flag": "⚠️", "pending": "⏳"}
                elab = {k: v[0] for k, v in emotion.STYLES.items()}
                return [[c["i"] + 1, icon.get(c["status"], c["status"]),
                         (c.get("style") if c.get("emo") == "custom" else elab.get(c.get("emo", "natural"), "")) or "",
                         c.get("dur", 0), c.get("attempts", 0),
                         (c.get("qc") or "") + (f" CER {c['cer']}" if c.get("cer") is not None else ""), c["text"]]
                        for c in jobs.load_job(jid)["chunks"]]

            def sel(jid):
                a, f = outputs_of(jid)
                return table(jid), a, f, (progress_text(jid) if jid else "")

            p_job.change(sel, p_job, [p_df, p_audio, p_files, p_prog])
            p_rf.click(lambda j: gr.update(choices=jobs.list_jobs(), value=j), p_job, p_job)

            def run(jid):
                try:
                    jobs.RUNNER.start(jid)
                    return "▶️ Đang chạy tiếp... (xem tiến độ bằng nút 🔄 hoặc ở tab Đọc kịch bản)", jid
                except Exception as e:
                    return _err(e), gr.update()

            p_run.click(run, p_job, [p_prog, cur_job])
            p_stop.click(lambda: (jobs.RUNNER.stop(), "⏸️ Sẽ dừng sau đoạn hiện tại")[1], None, p_prog)

            def exp(jid):
                try:
                    jobs.assemble(jobs.load_job(jid))
                    a, f = outputs_of(jid)
                    return "✅ Đã xuất lại", a, f
                except Exception as e:
                    return _err(e), None, None

            p_exp.click(exp, p_job, [p_prog, p_audio, p_files])

            def load_chunk(jid, i):
                try:
                    c = jobs.load_job(jid)["chunks"][int(i) - 1]
                    f = jobs.job_dir(jid) / "chunks" / c["file"] if c.get("file") else None
                    return c["text"], (str(f) if f and f.exists() else None)
                except Exception as e:
                    return _err(e), None

            def regen(jid, i, txt):
                if jobs.RUNNER.busy():
                    return gr.update(), None, "❌ Đang chạy dự án, hãy dừng trước."
                try:
                    c = jobs.regenerate_chunk(jid, int(i) - 1, txt)
                    return table(jid), str(jobs.job_dir(jid) / "chunks" / c["file"]), \
                        f"✅ Đã đọc lại đoạn {int(i)} ({c['dur']}s). Sửa xong các đoạn thì bấm **Ghép & xuất lại**."
                except Exception as e:
                    return gr.update(), None, _err(e)

            p_load.click(load_chunk, [p_job, p_idx], [p_text, p_caudio])
            p_regen.click(regen, [p_job, p_idx, p_text], [p_df, p_caudio, p_prog])

        # =============================================================== TAB 4: HỆ THỐNG
        with gr.Tab("🖥️ Hệ thống"):
            sys_md = gr.Markdown(engine.gpu_info())
            with gr.Row():
                gi = gr.Button("Kiểm tra GPU")
                ul = gr.Button("Giải phóng VRAM")
                op = gr.Button("📂 Mở thư mục kết quả")
            gr.Markdown(f"<span class='hint'>Thư mục: `{ROOT}` · Giới hạn VRAM: {SETTINGS.get('vram_limit_gb')} "
                        f"(sửa trong settings.json, \"auto\" = tự theo card) · Kết quả: `{OUTPUTS}`</span>")
            gr.Markdown("### 🔄 Cập nhật")
            with gr.Row():
                chk_btn = gr.Button("Kiểm tra cập nhật")
            chk_md = gr.Markdown(f"Phiên bản đang dùng: **v{updater.local_info().get('version')}**")
            gi.click(engine.gpu_info, None, sys_md)
            ul.click(lambda: (engine.unload_all(), engine.gpu_info())[1], None, sys_md)
            op.click(lambda: (os.startfile(str(OUTPUTS)) if os.name == "nt" else None, "📂 Đã mở")[1], None, sys_md)

        def upd_state(force=False):
            r = updater.check(force)
            if r["available"]:
                notes = (r["notes"] or "").replace("\n", "<br>")
                return (gr.update(visible=True),
                        f"🔔 **Có bản cập nhật mới v{r['remote']}** (đang dùng v{r['local']})<br><span class='hint'>{notes}</span>")
            return gr.update(visible=False), ""

        def on_check():
            r = updater.check(True)
            vis, md = upd_state()
            if r["error"]:
                txt = f"Phiên bản đang dùng: **v{r['local']}** · ⚠️ {r['error']}"
            elif r["available"]:
                txt = f"🔔 Có bản mới **v{r['remote']}** — bấm **Cập nhật ngay** ở đầu trang."
            else:
                txt = f"✅ Bạn đang dùng bản mới nhất (**v{r['local']}**)."
            return txt, vis, md

        chk_btn.click(on_check, None, [chk_md, upd_row, upd_md])

        def on_update():
            if jobs.RUNNER.busy() or lora.is_busy():
                return "❌ Đang đọc kịch bản hoặc huấn luyện. Đợi xong (hoặc dừng) rồi cập nhật.", gr.update()
            try:
                v = updater.apply()
                updater.restart()
                return (f"✅ Đã cập nhật lên **v{v}**. App đang khởi động lại — trang sẽ tự tải lại sau ít giây…",
                        gr.update(visible=False))
            except Exception as e:
                return _err(e), gr.update()

        upd_btn.click(on_update, None, [upd_msg, upd_row]).then(
            None, None, None, js="() => { setTimeout(() => location.reload(), 15000); }")
        upd_timer = gr.Timer(1800.0)
        upd_timer.tick(lambda: upd_state(True), None, [upd_row, upd_md], show_progress="hidden")

        def on_load():
            c = vchoices()
            return (gr.update(choices=c, value=None), gr.update(choices=voices.list_trash(), value=None),
                    gr.update(choices=vchoices("vi"), value=None),
                    gr.update(choices=jobs.list_jobs()))

        del_yes.click(do_delete, [del_target, s_lang, s_all], [del_box, del_target, t_voice, s_voice, tr_dd, v_msg])
        demo.load(on_load, None, [t_voice, tr_dd, s_voice, p_job])
        demo.load(lambda: upd_state(False), None, [upd_row, upd_md])
    return demo
