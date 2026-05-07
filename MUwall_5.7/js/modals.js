function initModals() {
    const getRedirectUrl = () => window.location.href.split('#')[0];

    const show = (id) => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'block';
    };

    const hide = (id) => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    };

    const hideAllModals = () => ['login-modal', 'post-modal', 'edit-profile-modal'].forEach(hide);

    const fillEditProfileForm = () => {
        const avatarInput = document.getElementById('edit-avatar-url');
        const majorInput = document.getElementById('edit-major');
        const bioInput = document.getElementById('edit-bio');
        if (!avatarInput || !majorInput || !bioInput) return;

        avatarInput.value = currentUser?.avatar || '';
        majorInput.value = currentUser?.major || '';
        bioInput.value = currentUser?.bio || '';
    };

    const setActiveAuthTab = (tab = 'login') => {
        const loginTab = document.getElementById('login-tab');
        const registerTab = document.getElementById('register-tab');

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });

        if (loginTab && registerTab) {
            loginTab.style.display = tab === 'login' ? 'block' : 'none';
            registerTab.style.display = tab === 'register' ? 'block' : 'none';
        }
    };

    document.querySelectorAll('.close').forEach(btn => {
        btn.onclick = () => hideAllModals();
    });

    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) hide(modal.id);
        });
    });

    ['login-btn', 'sidebar-login-btn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.onclick = () => {
                setActiveAuthTab('login');
                show('login-modal');
            };
        }
    });

    const createPostBtn = document.getElementById('create-post');
    if (createPostBtn) {
        createPostBtn.onclick = () => {
            if (!currentUser) {
                showToast('Please log in first.', 'error');
                setActiveAuthTab('login');
                return show('login-modal');
            }
            show('post-modal');
        };
    }

    const editProfileBtn = document.getElementById('open-edit-profile-btn');
    if (editProfileBtn) {
        editProfileBtn.onclick = () => {
            if (!currentUser) {
                showToast('Please log in first.', 'error');
                setActiveAuthTab('login');
                return show('login-modal');
            }
            fillEditProfileForm();
            show('edit-profile-modal');
        };
    }

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.onclick = () => setActiveAuthTab(btn.dataset.tab);
    });

    const regForm = document.getElementById('register-form');
    if (regForm) {
        regForm.onsubmit = async (e) => {
            e.preventDefault();

            const username = e.target.querySelector('#reg-username').value.trim();
            const email = e.target.querySelector('#reg-email').value.trim();
            const password = e.target.querySelector('#reg-password').value;
            const confirm = e.target.querySelector('#reg-confirm-password').value;
            const identity = e.target.querySelector('#reg-identity').value;

            if (!email || !password || !username) {
                return showToast('Please fill in all fields.', 'error');
            }
            if (password !== confirm) {
                return showToast('Passwords do not match.', 'error');
            }

            const submitBtn = e.target.querySelector('button[type="submit"]');
            if (!muwallDb) {
                return showToast('Supabase SDK did not load. Please refresh the page.', 'error', 5000);
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Registering...';
            }
            showToast('Registering account...', 'info', 1800);

            try {
                const { data, error } = await muwallDb.auth.signUp({
                    email,
                    password,
                    options: {
                        emailRedirectTo: getRedirectUrl(),
                        data: {
                            username,
                            identity,
                            avatar: 'icon/default.png',
                            major: '',
                            bio: ''
                        }
                    }
                });

                if (error) {
                    console.error('Sign up error:', error.message);
                    return showToast('Register failed: ' + error.message, 'error', 5000);
                }

                if (data.session && typeof syncCurrentUserFromSession === 'function') {
                    await syncCurrentUserFromSession(data.session);
                    try {
                        await saveUserProfile({
                            username,
                            identity,
                            avatar: 'icon/default.png',
                            major: '',
                            bio: ''
                        });
                    } catch (profileError) {
                        console.warn('Registered, but profile upsert failed:', profileError.message);
                    }
                    hide('login-modal');
                    showToast('Registered and logged in.', 'success');
                } else {
                    showToast('Registered. Please check your email to verify the account.', 'success', 4500);
                    setActiveAuthTab('login');
                }

                e.target.reset();
            } catch (error) {
                console.error('Unexpected register error:', error);
                showToast('Register error: ' + error.message, 'error', 5000);
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = '注册';
                }
            }
        };
    }

    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.onsubmit = async (e) => {
            e.preventDefault();

            const email = e.target.querySelector('#login-email').value.trim();
            const password = e.target.querySelector('#login-password').value;

            if (!email || !password) {
                return showToast('Please enter email and password.', 'error');
            }

            const submitBtn = e.target.querySelector('button[type="submit"]');
            if (!muwallDb) {
                return showToast('Supabase SDK did not load. Please refresh the page.', 'error', 5000);
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Logging in...';
            }

            try {
                const { data, error } = await muwallDb.auth.signInWithPassword({
                    email,
                    password
                });

                if (error) {
                    console.error('Login error:', error.message);
                    return showToast('Login failed: email or password is incorrect.', 'error');
                }

                if (data.session && typeof syncCurrentUserFromSession === 'function') {
                    await syncCurrentUserFromSession(data.session);
                }

                hide('login-modal');
                showToast('Login successful.', 'success');
            } catch (error) {
                console.error('Unexpected login error:', error);
                showToast('Login error: ' + error.message, 'error', 5000);
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = '登录';
                }
            }
        };
    }

    const googleLoginBtn = document.getElementById('google-login-btn');
    if (googleLoginBtn) {
        googleLoginBtn.onclick = async () => {
            const { error } = await muwallDb.auth.signInWithOAuth({
                provider: 'google',
                options: {
                    redirectTo: getRedirectUrl()
                }
            });

            if (error) {
                console.error('Google login error:', error.message);
                showToast('Google login failed: ' + error.message, 'error');
            }
        };
    }

    const editProfileForm = document.getElementById('edit-profile-form');
    if (editProfileForm) {
        editProfileForm.onsubmit = async (e) => {
            e.preventDefault();

            if (!currentUser) {
                showToast('Please log in first.', 'error');
                setActiveAuthTab('login');
                return show('login-modal');
            }

            const avatarUrl = document.getElementById('edit-avatar-url')?.value.trim();
            const major = document.getElementById('edit-major')?.value.trim() || '';
            const bio = document.getElementById('edit-bio')?.value.trim() || '';
            const submitBtn = e.target.querySelector('button[type="submit"]');

            if (submitBtn) submitBtn.disabled = true;

            try {
                const updatedUser = await saveUserProfile({
                    ...currentUser,
                    avatar: avatarUrl || currentUser.avatar || 'icon/default.png',
                    major,
                    bio
                });

                currentUser = updatedUser;
                setCurrentUser(updatedUser);
                if (typeof updateProfileUI === 'function') updateProfileUI(updatedUser);
                hide('edit-profile-modal');
                showToast('Profile saved to Supabase.', 'success');
            } catch (error) {
                console.error('Profile save error:', error);
                showToast('Profile save failed: ' + error.message, 'error', 4500);
            } finally {
                if (submitBtn) submitBtn.disabled = false;
            }
        };
    }
}
