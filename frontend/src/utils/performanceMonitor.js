/**
 * Performance monitoring and optimization utilities
 * Phase 3.3: Performance tracking for Core Web Vitals
 */

export const metrics = {
  lcp: null,
  fid: null,
  cls: null,
  fcp: null,
  ttfb: null,
};

/**
 * Initialize Core Web Vitals monitoring
 * Tracks LCP, FID, CLS, FCP, TTFB
 */
export function initPerformanceMonitoring() {
  // Largest Contentful Paint (LCP)
  if ('PerformanceObserver' in window) {
    try {
      const lcpObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const lastEntry = entries[entries.length - 1];
        metrics.lcp = lastEntry.renderTime || lastEntry.loadTime;
        logMetric('LCP', metrics.lcp);
      });
      lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });
    } catch (e) {
      console.warn('LCP observer not supported', e);
    }

    // First Input Delay (FID)
    try {
      const fidObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        entries.forEach((entry) => {
          metrics.fid = entry.processingDuration;
          logMetric('FID', metrics.fid);
        });
      });
      fidObserver.observe({ entryTypes: ['first-input'] });
    } catch (e) {
      console.warn('FID observer not supported', e);
    }

    // Cumulative Layout Shift (CLS)
    try {
      const clsObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        entries.forEach((entry) => {
          if (!entry.hadRecentInput) {
            metrics.cls = (metrics.cls || 0) + entry.value;
            logMetric('CLS', metrics.cls);
          }
        });
      });
      clsObserver.observe({ entryTypes: ['layout-shift'] });
    } catch (e) {
      console.warn('CLS observer not supported', e);
    }

    // First Contentful Paint (FCP) and Time to First Byte (TTFB)
    try {
      const paintObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        entries.forEach((entry) => {
          if (entry.name === 'first-contentful-paint') {
            metrics.fcp = entry.startTime;
            logMetric('FCP', metrics.fcp);
          }
        });
      });
      paintObserver.observe({ entryTypes: ['paint', 'navigation'] });

      if (performance.timing && performance.timing.responseStart > 0) {
        metrics.ttfb = performance.timing.responseStart - performance.timing.navigationStart;
        logMetric('TTFB', metrics.ttfb);
      }
    } catch (e) {
      console.warn('Paint observer not supported', e);
    }
  }
}

/**
 * Log metric value (only in development)
 */
function logMetric(name, value) {
  if (process.env.NODE_ENV === 'development') {
    console.log(`[METRIC] ${name}: ${Math.round(value)}ms`);
  }
}

/**
 * Measure component render time
 */
export function measureComponentRender(componentName) {
  const startMark = `${componentName}-start`;
  const endMark = `${componentName}-end`;

  return {
    start: () => performance.mark(startMark),
    end: () => {
      performance.mark(endMark);
      try {
        performance.measure(componentName, startMark, endMark);
        const measure = performance.getEntriesByName(componentName)[0];
        logMetric(`Render: ${componentName}`, measure.duration);
        return measure.duration;
      } catch (e) {
        console.warn('Performance measurement not supported', e);
      }
    },
  };
}

/**
 * Check if performance is degraded and adapt UI
 */
export function getPerformanceAdaptation() {
  const lcp = metrics.lcp || Infinity;
  const fid = metrics.fid || Infinity;
  const cls = metrics.cls || 1;

  return {
    isPerformant: lcp < 2500 && fid < 100 && cls < 0.1,
    quality: {
      particles: lcp > 2500 ? 0.5 : 1.0,
      blur: lcp > 3000 ? false : true,
      animations: fid > 100 ? false : true,
    },
  };
}

/**
 * Report metrics to analytics (if available)
 */
export function reportMetrics() {
  const data = {
    lcp: metrics.lcp,
    fid: metrics.fid,
    cls: metrics.cls,
    fcp: metrics.fcp,
    ttfb: metrics.ttfb,
    timestamp: new Date().toISOString(),
  };

  if (window.__metrics_endpoint) {
    fetch(window.__metrics_endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).catch(() => {});
  }
}
