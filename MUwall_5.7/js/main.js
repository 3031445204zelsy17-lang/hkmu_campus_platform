document.addEventListener('DOMContentLoaded', async () => {
    console.log('MUwall app started');

    initModals();
    setupSidebarDrawer();
    setupNavigation();
    setupFilterTabs();
    setupCategoryTabs();
    setupProfileTabs();
    setupSearchBox();

    await refreshUserProfileFromSupabase();
    updateProfileUI(currentUser);
    fetchAndRenderPosts();

    const logoutBtn = document.getElementById('logout-btn') || document.getElementById('profile-logout-btn');
    if (logoutBtn) {
        logoutBtn.onclick = async () => {
            await muwallDb.auth.signOut();
            setCurrentUser(null);
            currentUser = null;
            updateProfileUI(null);
            showToast('Logged out.', 'success');
        };
    }
});

function updateProfileUI(user) {
    const avatarEl = document.getElementById('profile-page-avatar');
    const nameEl = document.getElementById('profile-page-name');
    const majorEl = document.getElementById('profile-page-major');
    const bioEl = document.getElementById('profile-page-bio');
    const sidebarCard = document.querySelector('.user-card');
    const sidebarAvatar = sidebarCard ? sidebarCard.querySelector('img') : null;
    const sidebarName = sidebarCard ? sidebarCard.querySelector('h4') : null;
    const sidebarDesc = sidebarCard ? sidebarCard.querySelector('p') : null;
    const sidebarLoginBtn = document.getElementById('sidebar-login-btn');
    const navLoginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('profile-logout-btn');
    const editProfileBtn = document.getElementById('open-edit-profile-btn');
    const profilePostList = document.getElementById('profile-post-list');
    const profileView = document.getElementById('profile-view');

    if (user) {
        const identityLabel = user.identity === 'teacher' ? 'Teacher' : 'Student';
        const majorText = [identityLabel, user.major].filter(Boolean).join(' - ');
        const bioText = user.bio || 'No bio yet.';
        const avatarUrl = user.avatar || 'icon/default.png';

        if (avatarEl) avatarEl.src = avatarUrl;
        if (nameEl) nameEl.textContent = user.username || 'User';
        if (majorEl) majorEl.textContent = majorText || identityLabel;
        if (bioEl) bioEl.textContent = bioText;
        if (sidebarAvatar) sidebarAvatar.src = avatarUrl;
        if (sidebarName) sidebarName.textContent = user.username || 'User';
        if (sidebarDesc) sidebarDesc.textContent = bioText;
        if (sidebarLoginBtn) sidebarLoginBtn.style.display = 'none';
        if (navLoginBtn) navLoginBtn.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'inline-flex';
        if (editProfileBtn) editProfileBtn.style.display = 'inline-flex';
        if (profileView?.style.display === 'block' && typeof fetchCurrentUserPosts === 'function') {
            fetchCurrentUserPosts();
        }
    } else {
        if (avatarEl) avatarEl.src = 'icon/default.png';
        if (nameEl) nameEl.textContent = 'Not logged in';
        if (majorEl) majorEl.textContent = 'Login to view your profile';
        if (bioEl) bioEl.textContent = 'Create an account to publish posts and edit your profile.';
        if (sidebarAvatar) sidebarAvatar.src = 'icon/default.png';
        if (sidebarName) sidebarName.textContent = 'Not logged in';
        if (sidebarDesc) sidebarDesc.textContent = 'Login to view personal information';
        if (sidebarLoginBtn) sidebarLoginBtn.style.display = 'inline-flex';
        if (navLoginBtn) navLoginBtn.style.display = 'inline-flex';
        if (logoutBtn) logoutBtn.style.display = 'none';
        if (editProfileBtn) editProfileBtn.style.display = 'none';
        if (profilePostList) {
            profilePostList.innerHTML = '<div class="no-posts">Please log in to view your posts.</div>';
        }
    }
}

async function refreshUserProfileFromSupabase() {
    if (!muwallDb) return;

    const { data: { session } } = await muwallDb.auth.getSession();
    if (typeof syncCurrentUserFromSession === 'function') {
        await syncCurrentUserFromSession(session);
    }
}

function setupSidebarDrawer() {
    const toggle = document.getElementById('sidebar-toggle');
    const drawer = document.getElementById('drawer-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!toggle || !drawer || !overlay) return;

    const closeDrawer = () => {
        drawer.classList.remove('open');
        overlay.classList.remove('show');
    };

    toggle.onclick = () => {
        const willOpen = !drawer.classList.contains('open');
        drawer.classList.toggle('open');
        overlay.classList.toggle('show', willOpen);
    };

    overlay.onclick = closeDrawer;
}

function setupNavigation() {
    const navLinks = document.querySelectorAll('.navbar-menu a');
    const viewMap = {
        '#categories': 'categories-view',
        '#search': 'search-view',
        '#profile': 'profile-view'
    };

    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            const targetView = viewMap[link.getAttribute('href')] || 'home-view';
            if (typeof showView === 'function') showView(targetView);

            if (targetView === 'categories-view') {
                fetchAndRenderPosts({ targetSelector: '#category-posts' });
            }

            if (targetView === 'profile-view' && typeof fetchCurrentUserPosts === 'function') {
                fetchCurrentUserPosts();
            }
        });
    });

    if (typeof showView === 'function') showView('home-view');
}

function setupFilterTabs() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            fetchAndRenderPosts();
        });
    });
}

function setupCategoryTabs() {
    const categoryTabs = document.querySelectorAll('.category-tab');
    const categoryByI18nKey = {
        cat_all: 'all',
        cat_share: 'campus-share',
        cat_help: 'study-help',
        cat_life: 'daily-life',
        cat_news: 'campus-news',
        cat_qna: 'qna'
    };

    categoryTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            categoryTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const labelKey = tab.querySelector('[data-i18n]')?.dataset.i18n;
            const category = categoryByI18nKey[labelKey] || tab.dataset.category || 'all';

            fetchAndRenderPosts({
                targetSelector: '#category-posts',
                category
            });
        });
    });
}

function setupProfileTabs() {
    const tabs = document.querySelectorAll('.profile-tab');
    const panels = document.querySelectorAll('.tab-panel');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            panels.forEach(panel => panel.classList.remove('active'));

            tab.classList.add('active');
            const target = document.getElementById(`${tab.dataset.tab}-tab`);
            if (target) target.classList.add('active');

            if (tab.dataset.tab === 'posts' && typeof fetchCurrentUserPosts === 'function') {
                fetchCurrentUserPosts();
            }
        });
    });
}

function setupSearchBox() {
    const input = document.getElementById('search-input');
    const btn = document.getElementById('search-btn');
    const results = document.getElementById('search-results');

    const renderPlaceholder = (text) => {
        if (results) results.innerHTML = `<div class="no-posts">${text}</div>`;
    };

    const doSearch = () => {
        const keyword = input ? input.value.trim() : '';
        if (!keyword) return renderPlaceholder('Please enter a search keyword.');

        fetchAndRenderPosts({
            targetSelector: '#search-results',
            search: keyword
        });
    };

    if (btn) btn.addEventListener('click', doSearch);
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                doSearch();
            }
        });
    }
}
