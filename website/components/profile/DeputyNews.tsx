"use client";

import { ExternalLink } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import ProfileSection from "./ProfileSection";

interface Article {
  id: number;
  code: string | null;
  title: string;
  lead: string | null;
  friendlyUri: string | null;
  link: string;
  publishedDate: string | null;
  lastModifiedDate: string | null;
  mainCategory: string | null;
  articleType: string | null;
  exclusive: number;
  authors: string | null;
  pictureUrl: string | null;
  pictureCaption: string | null;
  pictureCredits: string | null;
  domain: string | null;
  uuid: string | null;
  createdAt: string;
  matchQuality: string;
  mentionCount: number;
}

interface DeputyNewsProps {
  deputyId: number;
}

const PAGE_SIZE = 20;

export default function DeputyNews({ deputyId }: DeputyNewsProps) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef(false);
  const pageRef = useRef(1);

  const fetchPage = useCallback(
    async (pageNum: number, append: boolean) => {
      const res = await fetch(
        `/api/deputy/${deputyId}/news?page=${pageNum}&limit=${PAGE_SIZE}`,
      );
      if (!res.ok) throw new Error("Failed to fetch");
      const data = await res.json();
      const newArticles = data.articles || [];
      setArticles((prev) => {
        if (!append) return newArticles;
        const seen = new Set(prev.map((a) => a.id));
        const uniqueNew = newArticles.filter((a) => !seen.has(a.id));
        return [...prev, ...uniqueNew];
      });
      setTotal(data.pagination?.total || 0);
      setHasMore(pageNum < (data.pagination?.totalPages || 1));
      pageRef.current = pageNum;
    },
    [deputyId],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    pageRef.current = 1;
    setHasMore(true);
    loadingRef.current = false;
    fetchPage(1, false).then(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (!hasMore || loadingRef.current || loading) return;
    loadingRef.current = true;
    const nextPage = pageRef.current + 1;
    fetchPage(nextPage, true).finally(() => {
      loadingRef.current = false;
    });
  }, [hasMore, loading, fetchPage]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          loadMore();
        }
      },
      { root: sentinel.parentElement, rootMargin: "200px" },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleDateString("pt-PT", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  };

  const domainLabel = (domain: string | null) => {
    if (!domain) return null;
    const labels: Record<string, string> = {
      expresso: "Expresso",
      publico: "Público",
    };
    return labels[domain.toLowerCase()] || domain;
  };

  const domainColor = (domain: string | null) => {
    if (!domain) return "bg-stone-200 text-stone-700";
    const colors: Record<string, string> = {
      expresso: "bg-amber-100 text-amber-800 border-amber-300",
      publico: "bg-blue-100 text-blue-800 border-blue-300",
    };
    return colors[domain.toLowerCase()] || "bg-stone-200 text-stone-700";
  };

  const stripHtml = (html: string | null) => {
    if (!html) return null;
    return html
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  };

  return (
    <ProfileSection variant="secondary" className="p-6 md:p-8">
      <div className="flex items-center justify-between mb-8">
        <h2 className="font-headline text-2xl font-semibold text-primary-container uppercase tracking-wider">
          Notícias
        </h2>
        {total > 0 && (
          <span className="font-label text-xs uppercase tracking-wider text-primary-container/60">
            {articles.length} de {total} notícias
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-6">
          {["a", "b", "c", "d"].map((id) => (
            <div
              key={`skeleton-${id}`}
              className="border-2 border-stone-900 bg-surface p-6 glossy-finish animate-pulse"
            >
              <div className="h-5 bg-stone-300 rounded w-3/4 mb-3" />
              <div className="h-4 bg-stone-300 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : articles.length === 0 ? (
        <p className="font-body text-on-surface-variant">
          Nenhuma notícia encontrada para este deputado.
        </p>
      ) : (
        <div className="space-y-6 max-h-[800px] overflow-y-auto pr-2 custom-scrollbar">
          {articles.map((article) => {
            const fullUrl = article.link.startsWith("http")
              ? article.link
              : `https://expresso.pt${article.link}`;

            return (
              <a
                key={article.id}
                href={fullUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="block border-2 border-stone-900 bg-surface p-6 glossy-finish hover:bg-surface-container transition-colors group"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      {article.domain && (
                        <span
                          className={`font-label text-sm uppercase tracking-wider px-3 py-1 border ${domainColor(article.domain)}`}
                        >
                          {domainLabel(article.domain)}
                        </span>
                      )}
                      {article.mainCategory && (
                        <span className="font-label text-sm uppercase tracking-wider text-on-surface-variant">
                          {article.mainCategory}
                        </span>
                      )}
                    </div>

                    <h3 className="font-body text-on-surface text-lg font-medium leading-snug mb-3 group-hover:text-primary-container transition-colors">
                      {article.title}
                    </h3>

                    {article.lead && (
                      <p className="font-body text-on-surface-variant text-base leading-relaxed mb-3 line-clamp-2">
                        {stripHtml(article.lead)}
                      </p>
                    )}

                    <div className="flex flex-wrap items-center gap-3">
                      {article.authors && (
                        <span className="font-label text-sm text-on-surface-variant">
                          {article.authors}
                        </span>
                      )}
                      {article.publishedDate && (
                        <span className="font-label text-sm text-on-surface-variant">
                          {formatDate(article.publishedDate)}
                        </span>
                      )}
                    </div>
                  </div>

                  <ExternalLink
                    size={18}
                    className="text-stone-400 group-hover:text-primary-container transition-colors shrink-0 mt-1"
                  />
                </div>
              </a>
            );
          })}

          {hasMore && (
            <div
              ref={sentinelRef}
              className="border-2 border-stone-900 bg-surface p-6 glossy-finish animate-pulse"
            >
              <div className="h-5 bg-stone-300 rounded w-3/4 mb-3" />
              <div className="h-4 bg-stone-300 rounded w-1/2" />
            </div>
          )}
        </div>
      )}
    </ProfileSection>
  );
}
