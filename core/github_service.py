import requests
import time
import platform
from typing import List, Dict, Optional
from config import Config


class GitHubService:
    """Service to interact with GitHub API for PocketBase releases"""
    
    def __init__(self):
        self.api_url = Config.GITHUB_API_URL
        self.cache_duration = Config.GITHUB_CACHE_DURATION
        self._cache = None
        self._cache_time = 0
    
    def get_releases(self, force_refresh: bool = False) -> List[Dict]:
        """
        Get PocketBase releases from GitHub API
        Returns list of releases with version and download URLs
        """
        # Check cache
        if not force_refresh and self._cache and (time.time() - self._cache_time) < self.cache_duration:
            return self._cache
        
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            releases_data = response.json()
            
            releases = []
            for release in releases_data:
                if release.get('draft') or release.get('prerelease'):
                    continue
                
                version = release.get('tag_name', '').lstrip('v')
                if not version:
                    continue
                
                assets: Dict[str, str] = {}
                for asset in release.get('assets', []):
                    name = asset.get('name', '').lower()
                    download_url = asset.get('browser_download_url')
                    
                    # Keep full OS+arch information so we can pick the right binary later
                    if 'linux_amd64' in name:
                        assets['linux_amd64'] = download_url
                    elif 'linux_arm64' in name:
                        assets['linux_arm64'] = download_url
                    elif 'darwin_amd64' in name:
                        assets['darwin_amd64'] = download_url
                    elif 'darwin_arm64' in name:
                        assets['darwin_arm64'] = download_url
                    elif 'windows_amd64' in name:
                        assets['windows_amd64'] = download_url
                
                if assets:
                    releases.append({
                        'version': version,
                        'name': release.get('name', version),
                        'published_at': release.get('published_at'),
                        'assets': assets
                    })
            
            # Update cache
            self._cache = releases
            self._cache_time = time.time()
            
            return releases
        
        except Exception as e:
            print(f"Error fetching releases: {e}")
            # Return cached data if available
            if self._cache:
                return self._cache
            return []
    
    def get_download_url(self, version: str, os_type: str) -> Optional[str]:
        """Get download URL for specific version and OS.

        os_type is a high-level OS key ('linux', 'darwin', 'windows').
        We choose the correct architecture (amd64/arm64) based on the
        current CPU so that, for example, Linux servers get the proper
        linux_amd64 vs linux_arm64 binary.
        """
        releases = self.get_releases()
        machine = platform.machine().lower()

        def pick_asset(assets: Dict[str, str], base_os: str) -> Optional[str]:
            preferred_keys: List[str] = []
            fallback_keys: List[str] = []

            if base_os == 'linux':
                if machine in ('x86_64', 'amd64'):
                    preferred_keys = ['linux_amd64']
                    fallback_keys = ['linux_arm64']
                elif machine in ('arm64', 'aarch64'):
                    preferred_keys = ['linux_arm64']
                    fallback_keys = ['linux_amd64']
                else:
                    preferred_keys = ['linux_amd64', 'linux_arm64']
            elif base_os == 'darwin':
                if machine in ('x86_64', 'amd64'):
                    preferred_keys = ['darwin_amd64']
                    fallback_keys = ['darwin_arm64']
                elif machine in ('arm64', 'aarch64'):
                    preferred_keys = ['darwin_arm64']
                    fallback_keys = ['darwin_amd64']
                else:
                    preferred_keys = ['darwin_amd64', 'darwin_arm64']
            elif base_os == 'windows':
                preferred_keys = ['windows_amd64']
            else:
                preferred_keys = [base_os]

            # Try preferred then fallback keys
            for key in preferred_keys + fallback_keys:
                url = assets.get(key)
                if url:
                    return url

            # Backward-compat: if older cache only has base_os key
            return assets.get(base_os)

        for release in releases:
            if release['version'] == version:
                assets = release.get('assets', {})
                return pick_asset(assets, os_type)

        return None
