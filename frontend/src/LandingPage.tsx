import { ArrowDown, ArrowRight, Check, ChevronRight, Layers3, ScanLine, Sparkles, WandSparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useSiteBranding } from "./SiteBranding";
import { api, ApiError, type UserSummary } from "./user-api";

const demos = [
  { name: "印花提取", icon: ScanLine, title: "好设计，不必困在产品里。", description: "从衣服、杯子、帆布袋等产品图片中还原平面图案，保留设计与色彩，输出透明 PNG。", before: "真实 T 恤原图", after: "透明印花 PNG", beforeImage: "/brand/shirt-source-v3.webp", afterImage: "/brand/shirt-print-v3.png", tool: "ai.extract_print" },
  { name: "电商主图", icon: Layers3, title: "同一件产品，形成一整组主图。", description: "从真实产品照片生成干净的商品展示图，保持产品外观、印花与材质在每一张图里一致。", before: "真实杯子原图", after: "电商主图", beforeImage: "/brand/mug-source-v3.webp", afterImage: "/brand/mug-commerce-v3.webp", tool: "ai.ecommerce" },
  { name: "高清重绘", icon: WandSparkles, title: "熟悉的设计，更清晰的细节。", description: "修复模糊和边缘锯齿，提升原图清晰度。保留主体、背景和构图，继续打磨已有作品。", before: "原始 T 恤照片", after: "高清重绘结果", beforeImage: "/brand/shirt-source-v3.webp", afterImage: "/brand/shirt-redraw-v3.webp", tool: "ai.redraw" },
  { name: "AI 生图", icon: Sparkles, title: "从一句描述，得到完整画面。", description: "输入画面描述，或加入参考图片，让 AI 生成可直接继续编辑的产品视觉。", before: "文字描述", after: "AI 生成结果", beforeImage: "", afterImage: "/brand/ai-generate-v3.webp", tool: "ai.generate", prompt: "高级 POD 产品摄影，象牙色卫衣、陶瓷杯与同款印花，冷灰工作室背景，真实材质与柔和侧光。" },
];

function DemoArt({ mode, result = false }: { mode: number; result?: boolean }) {
  const item = demos[mode];
  if (!result && mode === 3) {
    return <div className="landing-prompt-art"><small>TEXT PROMPT</small><p>{item.prompt}</p><span>AI IMAGE · 1024 × 1024</span></div>;
  }
  const src = result ? item.afterImage : item.beforeImage;
  const smallSrc = src.replace(/\.(?:png|jpe?g|webp)$/i, "-small.webp");
  return <div className={`landing-demo-art ${result && mode === 0 ? "checker" : ""}`}><img src={smallSrc} srcSet={`${smallSrc} 640w, ${src} 1200w`} sizes="(max-width: 760px) 44vw, (max-width: 1100px) 28vw, 30vw" alt={result ? item.after : item.before} loading="lazy" decoding="async" /></div>;
}

export function LandingPage() {
  const branding = useSiteBranding();
  const [user, setUser] = useState<UserSummary | null>(null);
  const [session, setSession] = useState<"checking" | "guest" | "member" | "unknown">("checking");
  const [registration, setRegistration] = useState(false);
  const [demo, setDemo] = useState(0);
  useEffect(() => {
    let active = true;
    let revision = 0;
    function refresh() {
      const current = ++revision;
      void api.currentUser().then(({ user: value }) => {
        if (active && current === revision) { setUser(value); setSession("member"); }
      }).catch((error: unknown) => {
        if (active && current === revision) {
          setSession(error instanceof ApiError && error.status === 401 ? "guest" : "unknown");
          setUser(null);
        }
      });
      void api.authOptions().then((value) => { if (active && current === revision) setRegistration(value.registration_enabled); }).catch(() => undefined);
    }
    const onVisibility = () => { if (document.visibilityState === "visible") refresh(); };
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    document.addEventListener("visibilitychange", onVisibility);
    return () => { active = false; window.removeEventListener("focus", refresh); window.removeEventListener("pageshow", refresh); document.removeEventListener("visibilitychange", onVisibility); };
  }, []);

  const guest = session === "guest";
  const startHref = guest ? registration ? "/register" : "/login" : "/app/pod";
  const startLabel = guest ? registration ? "创建账号，开始开发" : "登录并开始开发" : "进入产品开发";
  const brand = <a className="landing-brand" href="/" aria-label={`${branding.site_name} · 网站首页`}><img src={branding.logo_url} width="34" height="34" alt="" /><strong>{branding.site_name}</strong></a>;
  return <main className="landing-page">
    <nav className="landing-nav" aria-label="网站导航">{brand}<div className="landing-nav-sections"><a href="#effects">功能效果</a><a href="#workflow">使用流程</a></div><div className="landing-account">
      {session === "member" && <span className="landing-greeting">你好，{user?.display_name}</span>}
      {guest ? <><a href="/login">登录</a>{registration && <a className="landing-button small" href="/register">开始使用<ArrowRight size={15} /></a>}</> : <a className="landing-button small" href="/app/pod">进入产品开发<ArrowRight size={15} /></a>}
    </div></nav>
    <section className="landing-hero">
      <div className="landing-hero-copy"><span className="landing-eyebrow"><i />AI POD 产品开发与批量上架系统</span><h1>把真实胚件，<br />开发成<span>可审核商品。</span></h1><p>从产品创意、设计方案和印花主稿，<br className="landing-desktop-break" />到商品视觉与英文文案，全部沿着可追溯链路推进。</p><div className="landing-hero-actions"><a className="landing-button" href={startHref}>{startLabel}<ArrowRight size={18} /></a><a className="landing-text-link" href="#workflow">查看流程<ArrowDown size={16} /></a></div><div className="landing-benefits"><span><Check size={14} />真实胚件作为商品锚点</span><span><Check size={14} />每一步由人工审核确认</span></div></div>
      <div className="landing-hero-visual custom">
        <img className="landing-custom-art" src={branding.home_image_url} alt={`${branding.site_name} 产品创作展示`} fetchPriority="high" decoding="async" />
      </div>
    </section>
    <div className="landing-capabilities"><span>从胚件到商品资料</span><div><span>AI 胚件理解</span><i /><span>Product Ideas</span><i /><span>Print Master</span><i /><span>商品视觉</span><i /><span>英文文案</span></div></div>
    <section className="landing-effects" id="effects">
      <header className="landing-section-heading"><div><span className="landing-eyebrow">图片能力作为辅助</span><h2>为产品开发处理真实素材。</h2></div><p>提取、重绘和精修都保留为辅助能力，<br />不替代 POD 主流程。</p></header>
      <div className="landing-effect-layout"><div className="landing-effect-copy"><div className="landing-demo-tabs" role="tablist" aria-label="功能效果">{demos.map((item, index) => <button key={item.name} id={`demo-tab-${index}`} aria-controls="landing-demo-panel" type="button" role="tab" aria-selected={demo === index} tabIndex={demo === index ? 0 : -1} onClick={() => setDemo(index)} onKeyDown={(event) => {
        if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? demos.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + demos.length) % demos.length;
        setDemo(next); document.getElementById(`demo-tab-${next}`)?.focus();
      }}><item.icon size={16} />{item.name}</button>)}</div><span className="landing-effect-number">0{demo + 1} / THE DETAILS MATTER</span><h3>{demos[demo].title}</h3><p>{demos[demo].description}</p><a className="landing-text-link" href={guest ? startHref : `/app/studio?tool=${demos[demo].tool}`}>试试{demos[demo].name}<ChevronRight size={16} /></a><small>以下为真实图片处理样例，实际效果会随原图与参数变化。</small></div>
        <div className="landing-comparison" id="landing-demo-panel" role="tabpanel" aria-labelledby={`demo-tab-${demo}`}><figure><figcaption><i />{demos[demo].before}</figcaption><DemoArt mode={demo} /></figure><span className="landing-comparison-arrow"><ArrowRight size={20} /></span><figure><figcaption><i />{demos[demo].after}</figcaption><DemoArt mode={demo} result /></figure></div>
      </div>
    </section>
    <section className="landing-workflow" id="workflow"><header className="landing-section-heading"><div><span className="landing-eyebrow">产品开发主链路</span><h2>从参考图，到可审核的商品资料。</h2></div><Sparkles size={30} strokeWidth={1.2} /></header><div className="landing-steps">{[
      ["01", "建立真实胚件", "录入品类与材质，上传供应商或已确认的真实产品参考图。"],
      ["02", "筛选产品与设计", "生成产品创意和设计方案，人工采用后生成并锁定 Print Master。"],
      ["03", "完成商品资料", "基于同一胚件和 Print Master 生成商品视觉、审核结果并输出英文文案。"],
    ].map(([number, title, description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div></section>
    <section className="landing-closing"><div><span className="landing-eyebrow">从真实胚件开始</span><h2>把商品开发变成一条清晰链路。</h2></div><a className="landing-button" href={startHref}>{startLabel}<ArrowRight size={18} /></a></section>
    <footer className="landing-footer">{brand}<span>让产品开发有依据，让每一步可追溯。</span><a href="/app/pod">进入产品开发<ArrowRight size={14} /></a></footer>
  </main>;
}
