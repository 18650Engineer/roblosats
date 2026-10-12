import React from 'react';
import { useTranslation } from 'react-i18next';
import { List, ListItem, Divider, Typography } from '@mui/material';

interface Props {
  /** The order's coordinator's contact (its own email, or another way to reach it). */
  contact?: string;
}

// Each coordinator answers for its own disputes: the text names its contact, not RoboSats'.
const withContact = (text: string, contact?: string): string =>
  text.replace(/robosats@protonmail\.com|kilombino@proton\.me/g, contact ?? 'kilombino@proton.me');

export const DisputeLoserPrompt = ({ contact }: Props): React.JSX.Element => {
  const { t } = useTranslation();

  return (
    <List dense={true}>
      <Divider />
      <ListItem>
        <Typography variant='body2'>
          {withContact(
            t(
              'Unfortunately you have lost the dispute. If you think this is a mistake you can ask to re-open the case by contacting your coordinator. If you think your coordinator was unfair, please fill a claim via email to robosats@protonmail.com',
            ),
            contact,
          )}
        </Typography>
      </ListItem>
    </List>
  );
};

export default DisputeLoserPrompt;
