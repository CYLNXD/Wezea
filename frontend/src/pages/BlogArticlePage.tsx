import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Clock, Tag, Zap } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useLanguage } from '../i18n/LanguageContext';
import { apiClient } from '../lib/api';
import PageNavbar from '../components/PageNavbar';

interface Article {
  id: number;
  slug: string;
  title: string;
  meta_description: string | null;
  content_md: string;
  category: string | null;
  tags: string | null;
  author: string | null;
  reading_time_min: number | null;
  published_at: string | null;
}

interface ArticleSummary {
  id: number;
  slug: string;
  title: string;
  category: string | null;
  reading_time_min: number | null;
}

const T = {
  fr: {
    back: 'Retour au blog',
    related: 'Articles liés',
    cta: 'Scanner votre domaine',
    ctaSub: 'Vérifiez gratuitement la sécurité de votre infrastructure',
    notFound: 'Article introuvable',
    min: 'min de lecture',
  },
  en: {
    back: 'Back to blog',
    related: 'Related articles',
    cta: 'Scan your domain',
    ctaSub: 'Check your infrastructure security for free',
    notFound: 'Article not found',
    min: 'min read',
  },
};

export default function BlogArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  const { lang } = useLanguage();
  const navigate = useNavigate();
  const t = T[lang] || T.fr;

  const [article, setArticle] = useState<Article | null>(null);
  const [related, setRelated] = useState<ArticleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    setNotFound(false);
    apiClient.get(`/public/articles/${slug}`)
      .then(r => {
        setArticle(r.data);
        // Update page title & meta
        document.title = `${r.data.title} | Wezea Blog`;
        const metaDesc = document.querySelector('meta[name="description"]');
        if (metaDesc && r.data.meta_description) {
          metaDesc.setAttribute('content', r.data.meta_description);
        }
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [slug]);

  // Fetch related articles (same category)
  useEffect(() => {
    if (!article?.category) return;
    apiClient.get('/public/articles', { params: { category: article.category, limit: 4 } })
      .then(r => {
        const arts = (r.data.articles || []).filter((a: ArticleSummary) => a.slug !== slug);
        setRelated(arts.slice(0, 3));
      })
      .catch(() => {});
  }, [article?.category, slug]);

  if (loading) {
    return (
      <>
        <PageNavbar title="Blog" />
        <div className="min-h-screen pt-20 flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
        </div>
      </>
    );
  }

  if (notFound || !article) {
    return (
      <>
        <PageNavbar title="Blog" />
        <div className="min-h-screen pt-20 flex flex-col items-center justify-center gap-4">
          <p className="text-slate-400">{t.notFound}</p>
          <button onClick={() => navigate('/blog')} className="sku-btn-ghost text-sm">
            <ArrowLeft size={14} /> {t.back}
          </button>
        </div>
      </>
    );
  }

  const catColor: Record<string, string> = {
    dns: '#22d3ee', ssl: '#4ade80', headers: '#a78bfa',
    ports: '#f87171', compliance: '#fbbf24',
  };
  const color = catColor[article.category || ''] || '#94a3b8';

  return (
    <>
      <PageNavbar title="Blog" />
      <div className="min-h-screen pt-20 pb-16 px-4">
        <div className="max-w-3xl mx-auto">
          {/* Back link */}
          <button
            onClick={() => navigate('/blog')}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 mb-6 transition-colors"
          >
            <ArrowLeft size={12} /> {t.back}
          </button>

          {/* Article header */}
          <header className="mb-8">
            {article.category && (
              <span
                className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider mb-3 px-2 py-0.5 rounded-full"
                style={{ color, background: `${color}15`, border: `1px solid ${color}30` }}
              >
                <Tag size={9} />
                {article.category}
              </span>
            )}
            <h1 className="text-2xl sm:text-3xl font-bold text-white mb-3">{article.title}</h1>
            <div className="flex items-center gap-4 text-xs text-slate-500">
              {article.author && <span>{article.author}</span>}
              {article.reading_time_min && (
                <span className="flex items-center gap-1">
                  <Clock size={11} /> {article.reading_time_min} {t.min}
                </span>
              )}
              {article.published_at && (
                <span>
                  {new Date(article.published_at).toLocaleDateString(
                    lang === 'fr' ? 'fr-FR' : 'en-US',
                    { day: 'numeric', month: 'long', year: 'numeric' }
                  )}
                </span>
              )}
            </div>
          </header>

          {/* Article content (Markdown) */}
          <article className="prose prose-invert prose-sm max-w-none
            prose-headings:text-white prose-headings:font-semibold
            prose-h2:text-xl prose-h2:mt-8 prose-h2:mb-3
            prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-2
            prose-p:text-slate-300 prose-p:leading-relaxed
            prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:underline
            prose-strong:text-white
            prose-code:text-cyan-300 prose-code:bg-white/5 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
            prose-pre:bg-slate-900/50 prose-pre:border prose-pre:border-white/5 prose-pre:rounded-lg
            prose-li:text-slate-300
            prose-table:text-sm
            prose-th:text-slate-300 prose-th:border-white/10
            prose-td:text-slate-400 prose-td:border-white/5
          ">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {article.content_md}
            </ReactMarkdown>
          </article>

          {/* CTA Scanner */}
          <div className="sku-card mt-10 p-6 text-center">
            <Zap size={20} className="text-cyan-400 mx-auto mb-2" />
            <p className="text-white font-semibold mb-1">{t.cta}</p>
            <p className="text-xs text-slate-400 mb-4">{t.ctaSub}</p>
            <button onClick={() => navigate('/')} className="sku-btn-primary text-sm px-6 py-2">
              {t.cta}
            </button>
          </div>

          {/* Related articles */}
          {related.length > 0 && (
            <div className="mt-10">
              <h3 className="text-sm font-semibold text-slate-300 mb-4">{t.related}</h3>
              <div className="grid gap-3 sm:grid-cols-3">
                {related.map(r => (
                  <button
                    key={r.id}
                    onClick={() => navigate(`/blog/${r.slug}`)}
                    className="sku-card p-4 text-left hover:border-white/15 transition-all"
                  >
                    <p className="text-xs font-medium text-white line-clamp-2">{r.title}</p>
                    {r.reading_time_min && (
                      <p className="text-[10px] text-slate-500 mt-2 flex items-center gap-1">
                        <Clock size={9} /> {r.reading_time_min} min
                      </p>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
