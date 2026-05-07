const CATEGORY_LABELS = {
    'campus-share': 'Campus Share',
    'study-help': 'Study Help',
    'daily-life': 'Daily Life',
    'campus-news': 'Campus News',
    qna: 'Q&A'
};

function escapeHtml(value = '') {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function formatPostDate(value) {
    if (!value) return '';
    return new Date(value).toLocaleString();
}

function getCategoryLabel(category) {
    return CATEGORY_LABELS[category] || category || 'General';
}

function isPostOwner(post) {
    return Boolean(currentUser?.id && post?.user_id && String(post.user_id) === String(currentUser.id));
}

function postMatchesSearch(post, keyword) {
    if (!keyword) return true;

    const haystack = [
        post.title,
        post.content,
        post.author,
        post.category,
        getCategoryLabel(post.category)
    ].join(' ').toLowerCase();

    return haystack.includes(keyword.toLowerCase());
}

function renderPostList(container, posts) {
    container.innerHTML = '';

    if (!posts.length) {
        container.innerHTML = '<div class="no-posts">No posts found.</div>';
        return;
    }

    posts.forEach(post => {
        const canDeletePost = isPostOwner(post);
        const postEl = document.createElement('div');
        postEl.className = 'post';
        postEl.dataset.postId = post.id;
        postEl.innerHTML = `
            <div class="post-header">
                <div class="user-info">
                    <img src="${escapeHtml(post.author_avatar || 'icon/default.png')}" alt="Avatar">
                    <div>
                        <h4>${escapeHtml(post.author || 'Unknown User')}</h4>
                        <span>${escapeHtml(formatPostDate(post.created_at))} - ${escapeHtml(getCategoryLabel(post.category))}</span>
                    </div>
                </div>
                ${canDeletePost ? `
                    <button class="delete-post-btn glass-btn danger circle small" type="button" title="Delete post" aria-label="Delete post">
                        <i class="fas fa-trash"></i>
                    </button>
                ` : ''}
            </div>
            <div class="post-content">
                <h3>${escapeHtml(post.title)}</h3>
                <p>${escapeHtml(post.content)}</p>
            </div>
            <div class="post-actions">
                <button class="action-btn glass-btn rounded small" type="button">
                    <i class="fas fa-thumbs-up"></i>
                    <span>${Number(post.like_count || 0)}</span>
                </button>
                <button class="action-btn glass-btn rounded small" type="button">
                    <i class="fas fa-comment"></i>
                    <span>${Number(post.comment_count || 0)}</span>
                </button>
            </div>
        `;

        const avatarImg = postEl.querySelector('.user-info img');
        if (avatarImg) {
            avatarImg.style.cursor = 'pointer';
            avatarImg.onclick = () => showAuthorInfo(post);
        }

        const deleteBtn = postEl.querySelector('.delete-post-btn');
        if (deleteBtn) {
            deleteBtn.onclick = () => deletePost(post, deleteBtn);
        }

        container.appendChild(postEl);
    });
}

function removePostFromRenderedLists(postId) {
    const targetId = String(postId);

    document.querySelectorAll('.post[data-post-id]').forEach(postEl => {
        if (postEl.dataset.postId === targetId) postEl.remove();
    });

    document.querySelectorAll('.post-list').forEach(list => {
        if (!list.querySelector('.post') && !list.querySelector('.no-posts')) {
            list.innerHTML = '<div class="no-posts">No posts found.</div>';
        }
    });
}

async function deletePost(post, triggerButton) {
    if (!muwallDb) {
        return showToast('Supabase SDK did not load. Please refresh the page.', 'error', 5000);
    }

    const { data: { session } } = await muwallDb.auth.getSession();
    if (!session?.user || !isPostOwner(post)) {
        return showToast('You can only delete your own posts.', 'error');
    }

    if (!window.confirm('Delete this post? This cannot be undone.')) return;

    if (triggerButton) triggerButton.disabled = true;

    try {
        const { data, error } = await muwallDb
            .from('posts')
            .delete()
            .eq('id', post.id)
            .eq('user_id', session.user.id)
            .select('id');

        if (error) throw error;
        if (!data?.length) throw new Error('No matching post was deleted.');

        removePostFromRenderedLists(post.id);
        showToast('Post deleted.', 'success');
    } catch (error) {
        console.error('Delete post error:', error);
        showToast('Delete failed: ' + error.message, 'error', 5000);
        if (triggerButton) triggerButton.disabled = false;
    }
}

async function loadPosts({ category = 'all', search = '', userId = null } = {}) {
    if (!muwallDb) {
        throw new Error('Supabase SDK did not load.');
    }

    let query = muwallDb
        .from('posts')
        .select('*');

    if (userId) query = query.eq('user_id', userId);

    const { data, error } = await query.order('created_at', { ascending: false });

    if (error) throw error;

    return (data || [])
        .filter(post => category === 'all' || !category || post.category === category)
        .filter(post => postMatchesSearch(post, search));
}

window.fetchAndRenderPosts = async function(options = {}) {
    const {
        targetSelector = '#home-view .post-list',
        category = 'all',
        search = '',
        userId = null
    } = options;

    const postList = document.querySelector(targetSelector);
    if (!postList) return;

    postList.innerHTML = '<div class="loading">Loading posts from Supabase...</div>';

    try {
        const posts = await loadPosts({ category, search, userId });
        renderPostList(postList, posts);
    } catch (error) {
        console.error('Load posts error:', error);
        postList.innerHTML = `<div class="no-posts">Load failed: ${escapeHtml(error.message)}</div>`;
    }
};

window.fetchCurrentUserPosts = async function(targetSelector = '#profile-post-list') {
    const postList = document.querySelector(targetSelector);
    if (!postList) return;

    if (!currentUser?.id) {
        postList.innerHTML = '<div class="no-posts">Please log in to view your posts.</div>';
        return;
    }

    await fetchAndRenderPosts({
        targetSelector,
        userId: currentUser.id
    });
};

function showAuthorInfo(post) {
    const infoParts = [
        post.author ? `Name: ${post.author}` : null,
        post.author_identity ? `Identity: ${post.author_identity}` : null,
        post.author_major ? `Major: ${post.author_major}` : null,
        post.author_bio ? `Bio: ${post.author_bio}` : null
    ].filter(Boolean);

    showToast(infoParts.join(' - ') || 'No author profile information.', 'info', 4500);
}

document.addEventListener('submit', async (e) => {
    if (e.target.id !== 'post-form') return;

    e.preventDefault();

    if (!muwallDb) {
        return showToast('Supabase SDK did not load. Please refresh the page.', 'error', 5000);
    }

    const { data: { session } } = await muwallDb.auth.getSession();
    if (!session?.user || !currentUser) {
        return showToast('Please log in before posting.', 'error');
    }

    const title = e.target.querySelector('input').value.trim();
    const content = e.target.querySelector('textarea').value.trim();
    const category = e.target.querySelector('select').value;

    if (!title || !content) {
        return showToast('Title and content cannot be empty.', 'error');
    }

    const submitBtn = e.target.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;

    const payload = {
        user_id: session.user.id,
        title,
        content,
        category,
        author: currentUser.username || session.user.email?.split('@')[0] || 'User',
        author_avatar: currentUser.avatar || 'icon/default.png',
        author_identity: currentUser.identity || 'student',
        author_major: currentUser.major || '',
        author_bio: currentUser.bio || ''
    };

    const { error } = await muwallDb.from('posts').insert(payload);

    if (submitBtn) submitBtn.disabled = false;

    if (error) {
        console.error('Create post error:', error);
        return showToast('Post failed: ' + error.message, 'error', 5000);
    }

    showToast('Post published.', 'success');
    e.target.reset();

    const postModal = document.getElementById('post-modal');
    if (postModal) postModal.style.display = 'none';

    fetchAndRenderPosts();
    fetchCurrentUserPosts();
});
