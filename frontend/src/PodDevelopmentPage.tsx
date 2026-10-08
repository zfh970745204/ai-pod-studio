import {
  Archive,
  Boxes,
  Check,
  ChevronRight,
  FileImage,
  FileText,
  FolderPlus,
  ImagePlus,
  Lightbulb,
  LoaderCircle,
  Plus,
  RefreshCw,
  Sparkles,
  Upload,
  WandSparkles,
  X,
} from "lucide-react";
import { type ChangeEvent, type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ImageThumbnail } from "./ImageThumbnail";
import {
  api,
  type Asset,
  type PodBlank,
  type PodDesignConcept,
  type PodIdea,
  type PodImageSlot,
  type PodProductCopy,
  type PodProject,
  type PodProjectDetail,
} from "./user-api";

type BusyKey = string | null;

function messageOf(reason: unknown): string {
  return reason instanceof Error ? reason.message : "操作未完成，请稍后重试";
}

function dateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

export function PodDevelopmentPage() {
  const [blanks, setBlanks] = useState<PodBlank[]>([]);
  const [projects, setProjects] = useState<PodProject[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedBlankId, setSelectedBlankId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PodProjectDetail | null>(null);
  const [ideasCount, setIdeasCount] = useState<10 | 20 | 50>(20);
  const [selectedIdeas, setSelectedIdeas] = useState<Set<string>>(new Set());
  const [showBlankForm, setShowBlankForm] = useState(false);
  const [blankCategory, setBlankCategory] = useState("");
  const [blankMaterial, setBlankMaterial] = useState("");
  const [blankName, setBlankName] = useState("");
  const [busy, setBusy] = useState<BusyKey>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const selectedBlank = useMemo(() => blanks.find((item) => item.id === selectedBlankId) || detail?.blank || null, [blanks, detail?.blank, selectedBlankId]);

  const loadWorkspace = useCallback(async () => {
    const [nextBlanks, nextProjects, nextAssets] = await Promise.all([
      api.podBlanks({ limit: 100 }), api.podProjects({ limit: 100 }), api.assets("", { limit: 100 }),
    ]);
    setBlanks(nextBlanks.items);
    setProjects(nextProjects.items);
    setAssets(nextAssets.items);
    setSelectedBlankId((current) => current || nextBlanks.items[0]?.id || null);
    setSelectedProjectId((current) => current || nextProjects.items[0]?.id || null);
  }, []);

  const loadDetail = useCallback(async () => {
    if (!selectedProjectId) { setDetail(null); return; }
    setDetail(await api.podProject(selectedProjectId));
  }, [selectedProjectId]);

  useEffect(() => { void loadWorkspace().catch((reason) => setError(messageOf(reason))); }, [loadWorkspace]);
  useEffect(() => { void loadDetail().catch((reason) => setError(messageOf(reason))); }, [loadDetail]);

  async function run(key: string, action: () => Promise<unknown>, refresh = true) {
    setBusy(key); setError(""); setNotice("");
    try {
      await action();
      setNotice("操作已提交到任务中心。");
      if (refresh) { await loadWorkspace(); await loadDetail(); }
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(null);
    }
  }

  async function createBlank(event: FormEvent) {
    event.preventDefault();
    await run("blank-create", async () => {
      const result = await api.createPodBlank({ category: blankCategory, material: blankMaterial, name: blankName.trim() || undefined });
      setSelectedBlankId(result.blank.id); setBlankCategory(""); setBlankMaterial(""); setBlankName(""); setShowBlankForm(false);
    });
  }

  async function uploadReference(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedBlank) return;
    await run(`reference-${selectedBlank.id}`, async () => {
      const uploaded = await api.uploadAsset(file);
      await api.addPodBlankReference(selectedBlank.id, { asset_id: uploaded.asset.id, reference_role: selectedBlank.references.length ? "detail" : "primary" });
    });
  }

  async function createProject() {
    if (!selectedBlank) return;
    await run("project-create", async () => {
      const result = await api.createPodProject({ blank_id: selectedBlank.id });
      setSelectedProjectId(result.project.id);
    });
  }

  function toggleIdea(id: string) {
    setSelectedIdeas((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const adoptedConcepts = detail?.design_concepts.filter((item) => item.status === "adopted") || [];
  const currentProduct = detail?.products[0] || null;

  return (
    <main className="pod-dev-page">
      <header className="pod-dev-header">
        <div><span>产品中心 / AI 产品开发</span><h1>从胚件开发 POD 商品</h1></div>
        <div className="pod-dev-header-actions">
          <button className="user-secondary" onClick={() => void run("refresh", loadWorkspace)} type="button"><RefreshCw className={busy === "refresh" ? "spin" : ""} size={17} />刷新</button>
          <button className="user-primary" onClick={() => setShowBlankForm(true)} type="button"><Plus size={17} />新建胚件</button>
        </div>
      </header>

      {(notice || error) && <div className={error ? "pod-dev-message error" : "pod-dev-message"}>{error || notice}</div>}

      <div className="pod-dev-layout">
        <aside className="pod-dev-side">
          <section className="pod-dev-side-section">
            <header><span><Boxes size={17} />胚件库</span><b>{blanks.length}</b></header>
            <div className="pod-dev-list">
              {blanks.map((blank) => <button className={selectedBlank?.id === blank.id ? "selected" : ""} key={blank.id} onClick={() => { setSelectedBlankId(blank.id); setSelectedProjectId(null); setDetail(null); }} type="button"><span><strong>{blank.name}</strong><small>{blank.category} · {blank.material}</small></span><i>{blank.references.length}</i></button>)}
              {!blanks.length && <p className="pod-dev-empty">尚未创建胚件</p>}
            </div>
          </section>
          <section className="pod-dev-side-section">
            <header><span><FolderPlus size={17} />开发项目</span><b>{projects.length}</b></header>
            <div className="pod-dev-list">
              {projects.map((project) => <button className={selectedProjectId === project.id ? "selected" : ""} key={project.id} onClick={() => setSelectedProjectId(project.id)} type="button"><span><strong>{project.name}</strong><small>{stageLabel(project.current_stage)} · {dateTime(project.updated_at)}</small></span><ChevronRight size={15} /></button>)}
              {!projects.length && <p className="pod-dev-empty">选择胚件后创建项目</p>}
            </div>
          </section>
        </aside>

        <section className="pod-dev-content">
          {!detail ? <BlankOverview blank={selectedBlank} busy={busy} onAnalyze={() => selectedBlank && void run(`analyze-${selectedBlank.id}`, () => api.analyzePodBlank(selectedBlank.id))} onCreateProject={() => void createProject()} onUpload={uploadReference} /> : <DevelopmentWorkspace detail={detail} assets={assets} busy={busy} ideasCount={ideasCount} selectedIdeas={selectedIdeas} onIdeasCount={setIdeasCount} onToggleIdea={toggleIdea} onSelectAllIdeas={() => setSelectedIdeas(new Set(detail.ideas.filter((item) => item.status === "proposed").map((item) => item.id)))} onClearIdeas={() => setSelectedIdeas(new Set())} onRun={run} onReload={() => void loadDetail()} currentProduct={currentProduct} adoptedConcepts={adoptedConcepts} />}
        </section>
      </div>

      {showBlankForm && <div className="pod-dev-modal-layer"><form className="pod-dev-modal" onSubmit={(event) => void createBlank(event)}><header><span><small>胚件库</small><h2>新建胚件</h2></span><button aria-label="关闭" onClick={() => setShowBlankForm(false)} type="button"><X size={19} /></button></header><label>品类<input autoFocus maxLength={100} onChange={(event) => setBlankCategory(event.target.value)} placeholder="例如：毛毯" required value={blankCategory} /></label><label>材质<input maxLength={100} onChange={(event) => setBlankMaterial(event.target.value)} placeholder="例如：Fleece" required value={blankMaterial} /></label><label>名称 <small>可选</small><input maxLength={160} onChange={(event) => setBlankName(event.target.value)} placeholder="未填写时按品类和材质生成" value={blankName} /></label><footer><button className="user-secondary" onClick={() => setShowBlankForm(false)} type="button">取消</button><button className="user-primary" disabled={busy === "blank-create"} type="submit">{busy === "blank-create" ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}创建</button></footer></form></div>}
    </main>
  );
}

function BlankOverview({ blank, busy, onAnalyze, onCreateProject, onUpload }: { blank: PodBlank | null; busy: BusyKey; onAnalyze: () => void; onCreateProject: () => void; onUpload: (event: ChangeEvent<HTMLInputElement>) => void }) {
  if (!blank) return <div className="pod-dev-state"><Boxes size={30} /><strong>从胚件开始</strong><p>创建胚件时只需填写品类和材质，再上传真实参考图。</p></div>;
  const suggested = blank.suggested_attributes;
  return <>
    <section className="pod-blank-summary"><div className="pod-blank-visual">{blank.references[0] ? <ImageThumbnail id={blank.references[0].asset_id} alt={blank.name} /> : <FileImage size={34} />}</div><div><span>胚件</span><h2>{blank.name}</h2><dl><div><dt>品类</dt><dd>{blank.category}</dd></div><div><dt>材质</dt><dd>{blank.material}</dd></div><div><dt>真实参考图</dt><dd>{blank.references.length} 张</dd></div></dl></div><div className="pod-blank-actions"><label className="user-secondary"><Upload size={17} />上传参考图<input accept="image/png,image/jpeg,image/webp" hidden onChange={onUpload} type="file" /></label><button className="user-secondary" disabled={!blank.references.length || busy?.startsWith("analyze-")} onClick={onAnalyze} type="button">{busy?.startsWith("analyze-") ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}AI 分析</button><button className="user-primary" onClick={onCreateProject} type="button"><FolderPlus size={17} />开始开发</button></div></section>
    {Object.keys(suggested).length > 0 && <section className="pod-dev-band"><header><span><Sparkles size={17} />AI 胚件建议</span></header><div className="pod-suggestion-grid">{Object.entries(suggested).filter(([, value]) => typeof value === "string").slice(0, 6).map(([key, value]) => <div key={key}><small>{labelOf(key)}</small><strong>{String(value)}</strong></div>)}</div></section>}
    <section className="pod-dev-band"><header><span><ImagePlus size={17} />真实参考图</span></header><div className="pod-reference-strip">{blank.references.map((reference) => <div key={reference.id}><ImageThumbnail id={reference.asset_id} alt={reference.reference_role} /><small>{reference.reference_role === "primary" ? "主参考" : reference.reference_role === "detail" ? "细节参考" : "场景参考"}</small></div>)}{!blank.references.length && <p className="pod-dev-empty">上传供应商图片或已确认的产品图片后，才能启动 AI 理解。</p>}</div></section>
  </>;
}

function DevelopmentWorkspace({ detail, busy, ideasCount, selectedIdeas, onIdeasCount, onToggleIdea, onSelectAllIdeas, onClearIdeas, onRun, onReload, currentProduct, adoptedConcepts }: { detail: PodProjectDetail; assets: Asset[]; busy: BusyKey; ideasCount: 10 | 20 | 50; selectedIdeas: Set<string>; onIdeasCount: (value: 10 | 20 | 50) => void; onToggleIdea: (id: string) => void; onSelectAllIdeas: () => void; onClearIdeas: () => void; onRun: (key: string, action: () => Promise<unknown>, refresh?: boolean) => Promise<void>; onReload: () => void; currentProduct: PodProjectDetail["products"][number] | null; adoptedConcepts: PodDesignConcept[] }) {
  const activeCopy = detail.product_copies.find((item) => item.product_id === currentProduct?.id && item.status === "active") || null;
  const activeImageSet = detail.image_sets.find((item) => item.product_id === currentProduct?.id && item.status === "active") || null;
  const mainSlot = activeImageSet?.slots.find((item) => item.code === "product_main") || null;
  const productMainReviewed = Boolean(currentProduct?.primary_visual_asset_id) && (!activeImageSet || mainSlot?.status === "approved");
  return <>
    <section className="pod-project-bar"><div><span>开发项目</span><h2>{detail.project.name}</h2><small>{detail.blank.name} · {stageLabel(detail.project.current_stage)}</small></div><div><button className="user-secondary" onClick={onReload} type="button"><RefreshCw size={17} />刷新结果</button></div></section>
    <ol className="pod-stage-rail pod-stage-rail-six"><li className="done"><b>1</b><span>胚件</span></li><li className={detail.ideas.length ? "done" : ""}><b>2</b><span>产品创意</span></li><li className={detail.design_concepts.length ? "done" : ""}><b>3</b><span>设计方案</span></li><li className={detail.print_candidates.length ? "done" : ""}><b>4</b><span>印花</span></li><li className={detail.image_sets.some((item) => item.status === "active") ? "done" : detail.print_master ? "done" : ""}><b>5</b><span>商品视觉</span></li><li className={activeCopy ? "done" : ""}><b>6</b><span>商品文案</span></li></ol>

    <section className="pod-dev-band"><header><span><Lightbulb size={18} />产品创意</span><aside><select aria-label="创意数量" onChange={(event) => onIdeasCount(Number(event.target.value) as 10 | 20 | 50)} value={ideasCount}><option value={10}>10 个</option><option value={20}>20 个</option><option value={50}>50 个</option></select><button className="user-primary" disabled={busy === "ideas"} onClick={() => void onRun("ideas", () => api.generatePodIdeas(detail.project.id, ideasCount), false)} type="button">{busy === "ideas" ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}生成创意</button></aside></header>
      {detail.ideas.length > 0 && <div className="pod-bulk-bar"><span>已选择 {selectedIdeas.size} 项</span><button onClick={onSelectAllIdeas} type="button">全选待采用</button><button onClick={onClearIdeas} type="button">取消选择</button><button className="user-secondary" disabled={!selectedIdeas.size} onClick={() => void onRun("bulk-ideas", () => api.bulkUpdatePodIdeas([...selectedIdeas], "adopted"))} type="button"><Check size={16} />批量采用</button></div>}
      <div className="pod-idea-grid">{detail.ideas.map((idea) => <IdeaCard idea={idea} checked={selectedIdeas.has(idea.id)} busy={busy} onToggle={onToggleIdea} onRun={onRun} />)}{!detail.ideas.length && <p className="pod-dev-empty">生成后在这里筛选产品方向。</p>}</div>
    </section>

    <section className="pod-dev-band"><header><span><WandSparkles size={18} />设计方案</span><aside><b>{adoptedConcepts.length} 个已采用</b></aside></header><div className="pod-concept-grid">{detail.design_concepts.map((concept) => <ConceptCard concept={concept} busy={busy} onRun={onRun} />)}{!detail.design_concepts.length && <p className="pod-dev-empty">采用创意后，生成不同结构的设计方案。</p>}</div></section>

    <section className="pod-dev-band"><header><span><FileImage size={18} />印花候选</span><aside>{detail.print_master && <span className="pod-master-badge"><Check size={14} />Print Master 已锁定</span>}</aside></header><div className="pod-print-grid">{detail.print_candidates.map((candidate) => <article key={candidate.id}><ImageThumbnail id={candidate.asset_id} alt="印花候选" /><footer><span>候选图</span>{!detail.print_master && <button className="user-primary" disabled={busy === `master-${candidate.id}`} onClick={() => void onRun(`master-${candidate.id}`, () => api.approvePodPrintMaster(candidate.id))} type="button">{busy === `master-${candidate.id}` ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}锁定为 Master</button>}{detail.print_master?.print_candidate_id === candidate.id && <b>当前 Master</b>}</footer></article>)}{!detail.print_candidates.length && <p className="pod-dev-empty">采用设计方案后，每次生成 4 个印花候选。</p>}</div></section>

    <ImageSetWorkspace busy={busy} detail={detail} onReload={onReload} onRun={onRun} product={currentProduct} />
    <ProductCopyWorkspace busy={busy} canGenerate={productMainReviewed} copy={activeCopy} onRun={onRun} product={currentProduct} />
  </>;
}

function ImageSetWorkspace({ detail, busy, onRun, onReload, product }: { detail: PodProjectDetail; busy: BusyKey; onRun: (key: string, action: () => Promise<unknown>, refresh?: boolean) => Promise<void>; onReload: () => void; product: PodProjectDetail["products"][number] | null }) {
  const [selectedSlots, setSelectedSlots] = useState<Set<string>>(new Set());
  const imageSet = detail.image_sets.find((item) => item.product_id === product?.id && item.status === "active") || null;
  const slots = imageSet?.slots || [];
  const generatable = slots.filter((slot) => slot.status !== "approved");

  function toggleSlot(id: string) {
    setSelectedSlots((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  if (!detail.print_master || !product) {
    return <section className="pod-dev-band pod-visual-band"><header><span><ImagePlus size={18} />商品视觉</span></header><p className="pod-dev-empty">锁定一个 Print Master 后，才能规划并生成商品图片套组。</p></section>;
  }

  if (!imageSet) {
    return <section className="pod-dev-band pod-visual-band"><header><span><ImagePlus size={18} />商品视觉套组</span><span className={`pod-product-status ${product.status}`}>{productStatus(product.status)}</span></header><div className="pod-image-plan-empty"><div><Sparkles size={22} /><strong>先按胚件类别规划图片套组</strong><p>AI 会根据当前胚件、产品创意和锁定印花，生成适合此商品的主图、细节、场景或比例等图片槽位。</p></div><button className="user-primary" disabled={busy === "image-strategy"} onClick={() => void onRun("image-strategy", () => api.generatePodImageStrategy(product.id), false)} type="button">{busy === "image-strategy" ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}AI 规划图片套组</button></div>{product.primary_visual_asset_id && <div className="pod-legacy-visual"><ImageThumbnail id={product.primary_visual_asset_id} alt="已有商品主图" /><span><small>已有主图</small><strong>该主图保留在商品资产链中</strong><em>生成新的套组后，`product_main` 槽位会成为当前主图锚点。</em></span></div>}</section>;
  }

  return <section className="pod-dev-band pod-visual-band"><header><span><ImagePlus size={18} />商品视觉套组</span><aside><span className="pod-set-version">套组 V{imageSet.version}</span><button className="user-secondary" disabled={busy === "image-strategy"} onClick={() => void onRun("image-strategy", () => api.generatePodImageStrategy(product.id), false)} type="button">{busy === "image-strategy" ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}重新规划</button></aside></header>
    <div className="pod-set-summary"><div className="pod-visual-master"><ImageThumbnail id={detail.print_master.asset_id} alt="锁定的 Print Master" /><span><small>设计锚点</small><strong>锁定的 Print Master</strong><em>所有商品专属图均直接使用同一印花和真实胚件参考，不引用其他生成图。</em></span></div><div><small>套组策略</small><p>{String(imageSet.strategy_snapshot.rationale || "根据当前胚件和产品方向规划的商品图片序列。")}</p><dl><div><dt>图片槽位</dt><dd>{slots.length} 个</dd></div><div><dt>已生成</dt><dd>{slots.filter((slot) => slot.asset_id).length} 个</dd></div><div><dt>已审核</dt><dd>{slots.filter((slot) => slot.status === "approved").length} 个</dd></div></dl></div></div>
    <div className="pod-bulk-bar pod-slot-bulk"><span>已选择 {selectedSlots.size} 个可生成槽位</span><button onClick={() => setSelectedSlots(new Set(generatable.map((slot) => slot.id)))} type="button">全选可生成</button><button onClick={() => setSelectedSlots(new Set())} type="button">取消选择</button><button className="user-secondary" disabled={!selectedSlots.size || busy === "slots-bulk"} onClick={() => void onRun("slots-bulk", () => api.bulkGeneratePodImageSlots(product.id, [...selectedSlots]), false)} type="button">{busy === "slots-bulk" ? <LoaderCircle className="spin" size={16} /> : <ImagePlus size={16} />}批量生成</button></div>
    <div className="pod-slot-grid">{slots.map((slot) => <ImageSlotCard busy={busy} checked={selectedSlots.has(slot.id)} key={slot.id} onReload={onReload} onRun={onRun} onToggle={toggleSlot} product={product} slot={slot} />)}</div>
  </section>;
}

function ProductCopyWorkspace({ product, copy, canGenerate, busy, onRun }: { product: PodProjectDetail["products"][number] | null; copy: PodProductCopy | null; canGenerate: boolean; busy: BusyKey; onRun: (key: string, action: () => Promise<unknown>, refresh?: boolean) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sellingPoints, setSellingPoints] = useState("");
  const [keywords, setKeywords] = useState("");
  const [warnings, setWarnings] = useState("");
  useEffect(() => { setEditing(false); setTitle(copy?.product_title || ""); setDescription(copy?.product_description || ""); setSellingPoints((copy?.selling_points || []).join("\n")); setKeywords((copy?.search_keywords || []).join("\n")); setWarnings((copy?.content_warnings || []).join("\n")); }, [copy?.id, copy?.updated_at]);
  const list = (value: string) => value.split("\n").map((item) => item.trim()).filter(Boolean);

  if (!product) return <section className="pod-dev-band pod-copy-band"><header><span><FileText size={18} />商品文案</span></header><p className="pod-dev-empty">锁定 Print Master 并完成商品视觉后，才可生成商品文案。</p></section>;
  if (!canGenerate) return <section className="pod-dev-band pod-copy-band"><header><span><FileText size={18} />商品文案</span></header><p className="pod-dev-empty">完成当前商品主图的生成与 G2 审核后，可调用 AI 文案引擎。</p></section>;
  if (!copy) return <section className="pod-dev-band pod-copy-band"><header><span><FileText size={18} />商品文案</span><span className={`pod-product-status ${product.status}`}>{productStatus(product.status)}</span></header><div className="pod-copy-empty"><div><FileText size={22} /><strong>生成可编辑的英文商品文案</strong><p>基于已确认胚件属性、采用创意和设计方向生成标题、描述、卖点及搜索关键词；不生成未经确认的规格或承诺。</p></div><button className="user-primary" disabled={busy === "copy-generate"} onClick={() => void onRun("copy-generate", () => api.generatePodProductCopy(product.id), false)} type="button">{busy === "copy-generate" ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}AI 生成文案</button></div></section>;
  return <section className="pod-dev-band pod-copy-band"><header><span><FileText size={18} />商品文案</span><aside><span className="pod-set-version">文案 V{copy.version}</span><button className="user-secondary" disabled={busy === "copy-regenerate"} onClick={() => void onRun("copy-regenerate", () => api.generatePodProductCopy(product.id), false)} type="button">{busy === "copy-regenerate" ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}重新生成</button></aside></header><div className="pod-copy-card">{editing ? <div className="pod-copy-editor"><label>商品标题<input maxLength={200} onChange={(event) => setTitle(event.target.value)} value={title} /></label><label>商品描述<textarea maxLength={5000} onChange={(event) => setDescription(event.target.value)} value={description} /></label><label>卖点 <small>每行一项，至少 3 项</small><textarea onChange={(event) => setSellingPoints(event.target.value)} value={sellingPoints} /></label><label>搜索关键词 <small>每行一项，至少 5 项</small><textarea onChange={(event) => setKeywords(event.target.value)} value={keywords} /></label><label>待确认提示 <small>每行一项，可留空</small><textarea onChange={(event) => setWarnings(event.target.value)} value={warnings} /></label></div> : <div className="pod-copy-view"><div><small>商品标题</small><h3>{copy.product_title}</h3></div><div><small>商品描述</small><p>{copy.product_description}</p></div><div><small>卖点</small><ul>{copy.selling_points.map((item) => <li key={item}>{item}</li>)}</ul></div><div><small>搜索关键词</small><p className="pod-copy-keywords">{copy.search_keywords.map((item) => <span key={item}>{item}</span>)}</p></div>{copy.content_warnings.length > 0 && <div className="pod-copy-warnings"><small>待确认提示</small><ul>{copy.content_warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>}</div>}<footer>{editing ? <><button className="user-secondary" onClick={() => setEditing(false)} type="button">取消</button><button className="user-primary" disabled={busy === "copy-save"} onClick={() => void onRun("copy-save", () => api.updatePodProductCopy(copy.id, { product_title: title, product_description: description, selling_points: list(sellingPoints), search_keywords: list(keywords), content_warnings: list(warnings) }))} type="button">{busy === "copy-save" ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}保存文案</button></> : <><button className="user-secondary" onClick={() => setEditing(true)} type="button">编辑文案</button><button className="user-secondary" disabled={busy === "copy-archive"} onClick={() => void onRun("copy-archive", () => api.archivePodProductCopy(copy.id))} type="button"><Archive size={16} />归档版本</button><button className="user-primary" disabled={busy === "product-review"} onClick={() => void onRun("product-review", () => api.createPodReview({ target_type: "product", target_id: product.id, gate: "G3", decision: "approved" }))} type="button">{busy === "product-review" ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}商品审核通过</button></>}</footer></div></section>;
}

function ImageSlotCard({ slot, product, checked, busy, onToggle, onRun, onReload }: { slot: PodImageSlot; product: PodProjectDetail["products"][number]; checked: boolean; busy: BusyKey; onToggle: (id: string) => void; onRun: (key: string, action: () => Promise<unknown>, refresh?: boolean) => Promise<void>; onReload: () => void }) {
  const [editing, setEditing] = useState(false);
  const [scene, setScene] = useState(slot.scene_prompt);
  const [composition, setComposition] = useState(slot.composition_prompt);
  const [style, setStyle] = useState(slot.style_prompt);
  useEffect(() => { setScene(slot.scene_prompt); setComposition(slot.composition_prompt); setStyle(slot.style_prompt); }, [slot.id, slot.updated_at, slot.scene_prompt, slot.composition_prompt, slot.style_prompt]);
  const key = `slot-${slot.id}`;
  const slotStatus = imageSlotStatus(slot.status);
  return <article className={`pod-slot-card ${slot.status}`}><header><label><input checked={checked} disabled={slot.status === "approved"} onChange={() => onToggle(slot.id)} type="checkbox" /><span /></label><span className={`pod-slot-status ${slot.status}`}>{slotStatus}</span></header>{slot.asset_id ? <ImageThumbnail id={slot.asset_id} alt={slot.title} /> : <div className="pod-slot-placeholder"><FileImage size={28} /></div>}<div className="pod-slot-card-body"><div className="pod-slot-title"><div><small>{slot.code}</small><h3>{slot.title}</h3></div><span>{slot.scope === "product_specific" ? "商品专属" : "通用素材"}</span></div>{editing ? <div className="pod-slot-editor"><label>场景<input maxLength={1000} onChange={(event) => setScene(event.target.value)} value={scene} /></label><label>构图<input maxLength={1000} onChange={(event) => setComposition(event.target.value)} value={composition} /></label><label>视觉处理<input maxLength={1000} onChange={(event) => setStyle(event.target.value)} value={style} /></label></div> : <dl><div><dt>场景</dt><dd>{slot.scene_prompt}</dd></div><div><dt>构图</dt><dd>{slot.composition_prompt}</dd></div><div><dt>风格</dt><dd>{slot.style_prompt}</dd></div></dl>}<footer>{editing ? <><button className="user-secondary" onClick={() => setEditing(false)} type="button">取消</button><button className="user-primary" disabled={busy === `${key}-save`} onClick={() => void onRun(`${key}-save`, () => api.updatePodImageSlot(slot.id, { scene_prompt: scene, composition_prompt: composition, style_prompt: style }))} type="button">{busy === `${key}-save` ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}保存</button></> : <><button className="user-secondary" disabled={slot.status === "approved"} onClick={() => setEditing(true)} type="button">编辑提示词</button><button className="user-primary" disabled={slot.status === "approved" || busy === key} onClick={() => void onRun(key, () => api.generatePodImageSlot(product.id, slot.id), false)} type="button">{busy === key ? <LoaderCircle className="spin" size={16} /> : <ImagePlus size={16} />}{slot.asset_id ? "重新生成" : "生成"}</button></>}</footer>{slot.asset_id && slot.status !== "approved" && !editing && <button className="pod-slot-review" disabled={busy === `${key}-review`} onClick={() => void onRun(`${key}-review`, () => api.createPodReview({ target_type: "image_slot", target_id: slot.id, gate: "G2", decision: "approved" }))} type="button"><Check size={16} />G2 审核通过</button>}{slot.generation_job_id && !slot.asset_id && <button className="pod-slot-job" onClick={onReload} type="button">任务已提交，刷新查看结果</button>}</div></article>;
}

function IdeaCard({ idea, checked, busy, onToggle, onRun }: { idea: PodIdea; checked: boolean; busy: BusyKey; onToggle: (id: string) => void; onRun: (key: string, action: () => Promise<unknown>, refresh?: boolean) => Promise<void> }) {
  const risk = String(idea.infringement_risk.risk_level || "low");
  return <article className={`pod-idea-card ${idea.status}`}><header><label><input checked={checked} disabled={idea.status !== "proposed"} onChange={() => onToggle(idea.id)} type="checkbox" /><span /></label><span className={`pod-risk ${risk}`}>{risk === "high" ? "高风险" : risk === "medium" ? "需复核" : "低风险"}</span></header><h3>{idea.idea_name}</h3><dl><div><dt>人群</dt><dd>{idea.target_audience}</dd></div><div><dt>场景</dt><dd>{idea.use_case}</dd></div><div><dt>方向</dt><dd>{idea.recommended_style}</dd></div></dl><p>{idea.rationale}</p><footer>{idea.status === "proposed" && <><button className="user-secondary" onClick={() => void onRun(`idea-${idea.id}`, () => api.updatePodIdea(idea.id, "archived"))} type="button">归档</button><button className="user-primary" disabled={busy === `idea-${idea.id}`} onClick={() => void onRun(`idea-${idea.id}`, () => api.updatePodIdea(idea.id, "adopted"))} type="button"><Check size={16} />采用</button></>}{idea.status === "adopted" && <button className="user-primary" disabled={busy === `design-${idea.id}`} onClick={() => void onRun(`design-${idea.id}`, () => api.generatePodDesigns(idea.id), false)} type="button">{busy === `design-${idea.id}` ? <LoaderCircle className="spin" size={16} /> : <WandSparkles size={16} />}生成设计</button>}{idea.status === "archived" && <span>已归档</span>}</footer></article>;
}

function ConceptCard({ concept, busy, onRun }: { concept: PodDesignConcept; busy: BusyKey; onRun: (key: string, action: () => Promise<unknown>, refresh?: boolean) => Promise<void> }) {
  return <article className={`pod-concept-card ${concept.status}`}><header><span>{concept.status === "adopted" ? "已采用" : concept.status === "archived" ? "已归档" : "待选择"}</span><small>{concept.visual_style}</small></header><h3>{concept.design_name}</h3><dl><div><dt>构图</dt><dd>{concept.composition}</dd></div><div><dt>主体</dt><dd>{concept.main_subject}</dd></div><div><dt>色彩</dt><dd>{concept.color_palette}</dd></div></dl><footer>{concept.status === "proposed" && <><button className="user-secondary" onClick={() => void onRun(`concept-archive-${concept.id}`, () => api.updatePodConcept(concept.id, "archived"))} type="button">归档</button><button className="user-primary" disabled={busy === `concept-${concept.id}`} onClick={() => void onRun(`concept-${concept.id}`, () => api.updatePodConcept(concept.id, "adopted"))} type="button"><Check size={16} />采用</button></>}{concept.status === "adopted" && <button className="user-primary" disabled={busy === `print-${concept.id}`} onClick={() => void onRun(`print-${concept.id}`, () => api.generatePodPrints(concept.id), false)} type="button">{busy === `print-${concept.id}` ? <LoaderCircle className="spin" size={16} /> : <FileImage size={16} />}生成 4 个印花</button>}</footer></article>;
}

function stageLabel(value: string) { return ({ blank: "胚件准备", ideas: "创意探索", print_master: "印花已锁定", image_strategy: "图片套组规划" } as Record<string, string>)[value] || value; }
function productStatus(value: string) { return ({ drafting: "待生成主图", visual_ready: "主图待审核", review_pending: "文案待审核", approved: "审核通过", rejected: "已驳回" } as Record<string, string>)[value] || value; }
function imageSlotStatus(value: PodImageSlot["status"]) { return ({ planned: "待生成", generated: "待审核", approved: "已通过", rejected: "已驳回" } as Record<PodImageSlot["status"], string>)[value]; }
function labelOf(value: string) { return ({ product_type: "产品类型", visible_material_guess: "材质建议", product_shape: "产品形态", likely_print_method: "印刷方式" } as Record<string, string>)[value] || value; }
