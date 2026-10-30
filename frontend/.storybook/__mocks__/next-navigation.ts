export const useSearchParams = () => new URLSearchParams();
export const usePathname = () => "/search";
export const useRouter = () => ({
  push: () => {},
  replace: () => {},
  prefetch: () => {},
  back: () => {},
  forward: () => {},
  refresh: () => {},
});
