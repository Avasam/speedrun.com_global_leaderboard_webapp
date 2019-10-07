import React, { useState } from 'react';
import { Button, TextField, Link } from '@material-ui/core';

import SrcApiKeyLink from './src-api-key-link'
import User from '../models/User';
import './login-form.css';

type loginFormProps = {
  setCurrentUser: (currentUser: User) => void
}

const LoginForm: React.FC<loginFormProps> = (props: loginFormProps) => {
  const [srcApiKeyInput, setSrcApiKeyInput] = useState('');

  const login = () =>
    fetch(`${process.env.REACT_APP_BASE_URL}/api/login`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        srcApiKeyInput,
      })
    }).then(res => res.json())
      .then((res: { token: string, user: User }) => {
        console.log(res)
        if (!res.token) return
        localStorage.setItem('jwtToken', res.token);
        props.setCurrentUser(res.user);
      })

  return <>
    <div className='flex'>
      <TextField
        id='src-api-key'
        name='src-api-key'
        margin="normal"
        type='password'
        label='Enter your SRC API key'
        onChange={event => setSrcApiKeyInput(event.currentTarget.value)}
      />
      <Link
        href='https://www.speedrun.com/api/auth'
        target='src'
        rel='noreferrer'
      >What's my key?</Link>
    </div>
    <Button variant='contained' color='primary' onClick={() => login()}>Access my schedules</Button>
    <p>
      Don't trust the above link because SRC's api portal looks janky?
      <br />Fair enough, you can also access your api key through
      <br /> <SrcApiKeyLink></SrcApiKeyLink>
    </p>
    <label>Why do we need your API key?</label>
    <p>
      By using your key, it's possible to authenticate you to speedrun.com without ever asking for a password!
      <br />If something ever goes wrong or you believe someone is abusing your key, you can change it easily at any time.
      <br /> Once logged in, you can manage your schedules, which includes creating, modifying and sharing them!
    </p>
  </>
}

export default LoginForm;