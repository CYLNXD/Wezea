import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Clock, ArrowRight, Tag } from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import { apiClient } from '../lib/api';
import PageNavbar from '../components/PageNavbar';

const CATEGORIES = [
  { value: '', label: { fr: 'Tous', en: 'All' } },
  { value: 'dns', label: { fr: 'DNS', en: 'DNS' } },
  { value: 'ssl', label: { fr: 'SSL / TLS', en: 'SSL / TLS' } },
  { value: 'headers', label: { fr: 'Headers HTTP', en: 'HTTP Headers' } },
  { value: 'ports', label: { fr: 'Ports & Services', en: 'Ports & Services' } },
  { value: 'compliance', label: { fr: 'Conformité', en: 'Compliance' } },
];

interface ArticleSummary {
  id: number;
  slug: string;
  title: string;
  meta_description: string | null;
  category: string | null;
  tags: string | null;
  author: string | null;
  reading_time_min: number | null;
  published_at: string | null;
}

const T = {
  fr: {
    title: 'Blog Cybersécurité',
    subtitle: 'Guides pratiques et conseils pour sécuriser votre infrastructure',
    readMore: 'Lire l\'article',
    noArticles: 'Aucun article pour le moment.',
    min: 'min',
  },
  en: {
    title: 'Cybersecurity Blog',
    subtitle: 'Practical guides and tips to secure your infrastructure',
    readMore: 'Read article',
    noArticles: 'No articles yet.',
    min: 'min',
  },
};

export default function BlogPage() {
  const { lang } = useLanguage();
  const navigate = useNavigate();
  const t = T[lang] || T.fr;
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (category) params.category = category;
    apiClient.get('/public/articles', { params })
      .then(r => setArticles(r.data.articles || []))
      .catch(() => setArticles([]))
      .finally(() => setLoading(false));
  }, [category]);

  const catColor: Record<string, string> = {
    dns: '#22d3ee',
    ssl: '#4ade80',
    headers: '#a78bfa',
    ports: '#f87171',
    compliance: '#fbbf24',
  };

  return (
    <>
      <PageNavbar title="Blog" />
      <div className="min-h-screen pt-20 pb-16 px-4">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="text-center mb-10">
            <div className="inline-flex items-center gap-2 mb-3">
              <BookOpen size={28} className="text-cyan-400" />
              <h1 className="text-3xl font-bold text-white">{t.title}</h1>
            </div>
            <p className="text-slate-400 text-sm">{t.subtitle}</p>
          </div>

          {/* Category filter */}
          <div className="flex flex-wrap gap-2 justify-center mb-8">
            {CATEGORIES.map(cat => (
              <button
                key={cat.value}
                onClick={() => setCategory(cat.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  category === cat.value
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
                }`}
              >
                {cat.label[lang] || cat.label.fr}
              </button>
            ))}
          </div>

          {/* Articles grid */}
          {loading ? (
            <div className="flex justify-center py-20">
              <div className="w-8 h-8 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
            </div>
          ) : articles.length === 0 ? (
            <p className="text-center text-slate-500 py-20">{t.noArticles}</p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {articles.map(article => {
                const color = catColor[article.category || ''] || '#94a3b8';
                return (
                  <button
                    key={article.id}
                    onClick={() => navigate(`/blog/${article.slug}`)}
                    className="sku-card text-left p-5 hover:border-white/15 transition-all group"
                  >
                    {/* Category badge */}
                    {article.category && (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider mb-3 px-2 py-0.5 rounded-full"
                        style={{
                          color,
                          background: `${color}15`,
                          border: `1px solid ${color}30`,
                        }}
                      >
                        <Tag size={9} />
                        {article.category}
                      </span>
                    )}

                    <h2 className="text-base font-semibold text-white mb-2 group-hover:text-cyan-300 transition-colors">
                      {article.title}
                    </h2>

                    {article.meta_description && (
                      <p className="text-xs text-slate-400 mb-3 line-clamp-2">
                        {article.meta_description}
                      </p>
                    )}

                    <div className="flex items-center justify-between mt-auto">
                      <div className="flex items-center gap-3 text-[10px] text-slate-500">
                        {article.reading_time_min && (
                          <span className="flex items-center gap-1">
                            <Clock size={10} />
                            {article.reading_time_min} {t.min}
                          </span>
                        )}
                        {article.published_at && (
                          <span>
                            {new Date(article.published_at).toLocaleDateString(
                              lang === 'fr' ? 'fr-FR' : 'en-US',
                              { day: 'numeric', month: 'short', year: 'numeric' }
                            )}
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-cyan-400/60 group-hover:text-cyan-400 flex items-center gap-1 transition-colors">
                        {t.readMore} <ArrowRight size={10} />
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
